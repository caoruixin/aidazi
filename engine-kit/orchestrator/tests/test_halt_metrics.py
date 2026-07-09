"""Tests for the Phase-3 halt-conditions metric registry (halt_metrics.py) — the
pure single-source-of-truth for the closed whitelist, digest, ack keys, and the
EP-pre evaluator. stdlib unittest; fully offline/deterministic."""
import os
import sys
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)                    # orchestrator/
if _ORCH_DIR not in sys.path:
    sys.path.insert(0, _ORCH_DIR)

import halt_metrics as hm  # noqa: E402


class RegistryTests(unittest.TestCase):
    def test_whitelist_is_the_three_structural_metrics(self):
        self.assertEqual(set(hm.METRIC_NAMES),
                         {"milestone_id", "subsprint_id", "milestone_functional_acceptance"})

    def test_ack_scopes(self):
        self.assertEqual(hm.METRICS["milestone_id"].ack_scope, hm.ACK_SCOPE_MILESTONE)
        self.assertEqual(hm.METRICS["subsprint_id"].ack_scope, hm.ACK_SCOPE_SUBSPRINT)
        self.assertEqual(hm.METRICS["milestone_functional_acceptance"].ack_scope,
                         hm.ACK_SCOPE_MILESTONE)

    def test_ops_closed(self):
        self.assertEqual(hm.OPS, frozenset({"==", "!=", "in", "not_in"}))


class ValidateWhenTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(hm.validate_when({"metric": "milestone_id", "op": "==", "value": "m2"}), [])
        self.assertEqual(hm.validate_when(
            {"metric": "subsprint_id", "op": "in", "value": ["s1", "s2"]}), [])
        self.assertEqual(hm.validate_when(
            {"metric": "milestone_functional_acceptance", "op": "!=", "value": "static"}), [])

    def _rules(self, when):
        return [r for r, _ in hm.validate_when(when)]

    def test_unknown_metric(self):
        self.assertIn("halt_condition_unknown_metric",
                      self._rules({"metric": "files_changed", "op": "==", "value": "x"}))

    def test_op_mismatch(self):
        self.assertIn("halt_condition_op_mismatch",
                      self._rules({"metric": "milestone_id", "op": ">", "value": "x"}))

    def test_value_type_enum(self):
        self.assertIn("halt_condition_value_type",
                      self._rules({"metric": "milestone_functional_acceptance",
                                   "op": "==", "value": "nope"}))

    def test_in_needs_nonempty_array(self):
        self.assertIn("halt_condition_value_type",
                      self._rules({"metric": "milestone_id", "op": "in", "value": "x"}))
        self.assertIn("halt_condition_value_type",
                      self._rules({"metric": "milestone_id", "op": "in", "value": []}))

    def test_scalar_op_rejects_array(self):
        self.assertIn("halt_condition_value_type",
                      self._rules({"metric": "milestone_id", "op": "==", "value": ["a"]}))

    def test_when_not_object(self):
        self.assertIn("halt_condition_when_shape", self._rules("nope"))


class DigestTests(unittest.TestCase):
    def test_in_array_order_independent(self):
        a = hm.condition_digest({"metric": "milestone_id", "op": "in", "value": ["b", "a"]})
        b = hm.condition_digest({"metric": "milestone_id", "op": "in", "value": ["a", "b"]})
        self.assertEqual(a, b)

    def test_predicate_change_changes_digest(self):
        a = hm.condition_digest({"metric": "milestone_id", "op": "==", "value": "x"})
        b = hm.condition_digest({"metric": "milestone_id", "op": "==", "value": "y"})
        c = hm.condition_digest({"metric": "milestone_id", "op": "!=", "value": "x"})
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)

    def test_deterministic(self):
        w = {"metric": "subsprint_id", "op": "in", "value": ["s2", "s1"]}
        self.assertEqual(hm.condition_digest(w), hm.condition_digest(dict(w)))


class AckKeyTests(unittest.TestCase):
    def test_milestone_scope_drops_subsprint(self):
        cond = {"id": "hot", "when": {"metric": "milestone_id", "op": "==", "value": "m2"}}
        key = hm.ack_key(cond, {"milestone_id": "m2", "subsprint_id": "s1"})
        self.assertEqual(len(key), 3)
        self.assertEqual(key[0], "hot")
        self.assertEqual(key[2], "m2")

    def test_subsprint_scope_includes_subsprint(self):
        cond = {"id": "s", "when": {"metric": "subsprint_id", "op": "==", "value": "s1"}}
        key = hm.ack_key(cond, {"milestone_id": "m2", "subsprint_id": "s1"})
        self.assertEqual(len(key), 4)
        self.assertEqual(key[3], "s1")


class EvaluateTests(unittest.TestCase):
    def setUp(self):
        self.conds = [
            {"id": "hot", "when": {"metric": "milestone_id", "op": "in", "value": ["m2"]}},
            {"id": "e2e", "when": {"metric": "milestone_functional_acceptance",
                                   "op": "==", "value": "browser_e2e"}},
        ]
        self.ctx = {"milestone_id": "m2", "subsprint_id": "s1",
                    "milestone_functional_acceptance": "browser_e2e"}

    def test_first_declaration_order_match(self):
        m = hm.evaluate(self.conds, self.ctx, [])
        self.assertEqual(m["condition_id"], "hot")
        self.assertEqual(m["facts"], {"milestone_id": "m2"})

    def test_ack_skips_to_next(self):
        m1 = hm.evaluate(self.conds, self.ctx, [])
        m2 = hm.evaluate(self.conds, self.ctx, [m1["ack_key"]])
        self.assertEqual(m2["condition_id"], "e2e")

    def test_all_acked_returns_none(self):
        m1 = hm.evaluate(self.conds, self.ctx, [])
        m2 = hm.evaluate(self.conds, self.ctx, [m1["ack_key"]])
        self.assertIsNone(hm.evaluate(self.conds, self.ctx, [m1["ack_key"], m2["ack_key"]]))

    def test_no_match_returns_none(self):
        ctx = {"milestone_id": "m1", "subsprint_id": "s1",
               "milestone_functional_acceptance": "static"}
        self.assertIsNone(hm.evaluate(self.conds, ctx, []))

    def test_empty_conditions_returns_none(self):
        self.assertIsNone(hm.evaluate([], self.ctx, []))

    def test_not_in_and_neq(self):
        conds = [{"id": "x", "when": {"metric": "subsprint_id", "op": "not_in",
                                      "value": ["s9"]}}]
        self.assertIsNotNone(hm.evaluate(conds, self.ctx, []))
        conds = [{"id": "x", "when": {"metric": "milestone_id", "op": "!=", "value": "m1"}}]
        self.assertIsNotNone(hm.evaluate(conds, self.ctx, []))


if __name__ == "__main__":
    unittest.main()

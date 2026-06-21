#!/usr/bin/env python3
"""e2e_app — a tiny deterministic, OFFLINE fixture web app for the browser-E2E executor.

The orchestrator-owned ``LocalHttpExecutor`` (engine-kit/orchestrator/e2e_executor.py)
starts THIS app as a subprocess, polls its readiness URL, drives a handful of user
journeys over stdlib HTTP, and captures evidence. It is the offline stand-in for "a
real product under test" so the whole P-C browser-E2E flow can be exercised with zero
network, zero billed calls, and fully reproducible output (same discipline as
fixtures/fake_eval.py for the static F5 path).

It is a pure ``http.server`` app — NO third-party deps. Determinism is the contract:
there is NO clock and NO randomness anywhere in a response body or in any state that
the executor hashes. The only configuration is the launch triple ``(--port, --store,
--mode)``; every byte a route emits is a pure function of (route, method, posted form,
the persisted store, mode).

Routes (the shapes the executor and its checklist depend on):
  - ``GET  /``          → an HTML form page with STABLE element ids
                          (``#name-input``, ``#submit-btn``, ``#status``).
  - ``POST /submit``    → behavior varies by --mode (below). The happy path persists
                          the posted ``name`` to the JSON store and 303-redirects to
                          ``/result``.
  - ``GET  /result``    → the success page; shows the persisted value in
                          ``#result-value`` with the text "Saved". It references the
                          ``/api/data`` sub-resource (so a net_fail there is observable
                          from the result journey).
  - ``GET  /api/data``  → a small JSON sub-resource the result page references.
  - ``GET  /__console`` → the app's CONSOLE SINK: a JSON list of console messages
                          ``[{level, text}, ...]`` (the offline analog of a real
                          browser console — the executor reads it for
                          ``assert_no_console_error``). DETERMINISTIC: the list is a
                          pure function of mode (no append-on-request side effects that
                          would make it order/timing dependent).
  - ``GET  /__state``   → the app's BACKEND STATE: the current store as JSON
                          (the executor reads it for ``assert_state`` — to catch a UI
                          that claims success while the backend disagrees).

Modes (``--mode``), each a single deterministic product behavior:
  - ``normal``         — happy path; everything works.
  - ``render_defect``  — ``/result`` OMITS ``#result-value`` and shows an error banner
                         (a visible FRONTEND defect; the value WAS persisted).
  - ``state_mismatch`` — ``/submit`` returns the success page but does NOT persist to
                         the store (the UI says saved; ``/__state`` disagrees).
  - ``console_error``  — ``/__console`` carries an ``error``-level entry (happy path
                         otherwise).
  - ``net_fail``       — ``/api/data`` returns HTTP 500 (a failed critical sub-resource;
                         happy path otherwise).

The store is a JSON file at ``--store``; an absent/empty file reads as the empty store
``{}``. Writes are last-write-wins and synchronous (single-threaded server), so
``/__state`` always reflects exactly what ``/submit`` persisted.
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import sys
import urllib.parse
from typing import Optional

# The set of modes the app understands. Kept here (not just in argparse) so the
# importable handler can fail closed on a bogus mode the same way the CLI does.
MODES = ("normal", "render_defect", "state_mismatch", "console_error", "net_fail")


def _read_store(store_path: str) -> dict:
    """Return the persisted store as a dict. Absent/empty/corrupt → ``{}``.

    Fail-soft on read (a missing store before the first /submit is the normal
    cold-start), never on the structural contract: the result is always a dict so
    every caller can index it without a type guard.
    """
    if not store_path or not os.path.exists(store_path):
        return {}
    try:
        with open(store_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_store(store_path: str, data: dict) -> None:
    """Persist the store deterministically (``sort_keys`` → byte-stable for hashing)."""
    with open(store_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, sort_keys=True, indent=2)


def _console_messages(mode: str) -> list:
    """The console sink contents for a mode — a pure function of mode (deterministic).

    The happy modes emit a single benign ``info`` line; ``console_error`` adds one
    ``error`` entry. There is intentionally NO per-request mutation: the executor must
    read the same console regardless of how many times it polls.
    """
    msgs = [{"level": "info", "text": "app ready"}]
    if mode == "console_error":
        msgs.append({"level": "error",
                     "text": "Uncaught TypeError: cannot read property of undefined"})
    return msgs


def _page_index() -> str:
    """The form page. Stable element ids are the executor's anchors."""
    return (
        "<!doctype html><html><head><title>e2e fixture</title></head><body>"
        "<h1 id=\"title\">Submit your name</h1>"
        "<form id=\"submit-form\" method=\"post\" action=\"/submit\">"
        "<input id=\"name-input\" name=\"name\" type=\"text\" value=\"\">"
        "<button id=\"submit-btn\" type=\"submit\">Submit</button>"
        "</form>"
        "<p id=\"status\">ready</p>"
        "</body></html>"
    )


def _page_result_ok(value: str) -> str:
    """The success page. ``#result-value`` carries the persisted value; the literal
    text "Saved" is what the checklist asserts for the happy path."""
    safe = _escape(value)
    return (
        "<!doctype html><html><head><title>result</title></head><body>"
        "<h1 id=\"result-title\">Result</h1>"
        f"<p id=\"result-value\">Saved: {safe}</p>"
        "<p id=\"status\">ok</p>"
        # references the sub-resource so a net_fail on /api/data is reachable from here
        "<script src=\"/api/data\"></script>"
        "</body></html>"
    )


def _page_result_render_defect() -> str:
    """The render_defect success page: NO ``#result-value`` element, an error banner
    instead. The value was persisted (state is fine); the FRONTEND is broken."""
    return (
        "<!doctype html><html><head><title>result</title></head><body>"
        "<h1 id=\"result-title\">Result</h1>"
        "<p id=\"error-banner\">Something went wrong rendering your result.</p>"
        "<p id=\"status\">error</p>"
        "<script src=\"/api/data\"></script>"
        "</body></html>"
    )


def _escape(text: str) -> str:
    """Minimal HTML-escape (stdlib-only, deterministic). Enough for the fixture's
    single user-supplied field — we never inject markup, so this stays tiny."""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("\"", "&quot;"))


class E2EAppHandler(http.server.BaseHTTPRequestHandler):
    """The fixture's request handler. ``mode`` and ``store_path`` are bound onto the
    server instance (see :func:`make_server`) so this class stays import-safe and the
    process is configured purely by the launch triple."""

    # Silence the default per-request stderr logging — the executor captures the
    # subprocess's stderr into app-start.log/app-stop.log and noisy access lines
    # would make that artifact non-deterministic (they embed timestamps).
    def log_message(self, fmt, *args):  # noqa: A003 - overriding stdlib signature
        return

    # -- helpers ----------------------------------------------------------------- #
    @property
    def mode(self) -> str:
        return getattr(self.server, "mode", "normal")

    @property
    def store_path(self) -> str:
        return getattr(self.server, "store_path", "")

    def _send_html(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, status: int, obj) -> None:
        payload = json.dumps(obj, sort_keys=True, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    # -- routes ------------------------------------------------------------------ #
    def do_GET(self):  # noqa: N802 - stdlib http.server naming
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_html(200, _page_index())
        elif path == "/result":
            self._get_result()
        elif path == "/api/data":
            self._get_api_data()
        elif path == "/__console":
            self._send_json(200, _console_messages(self.mode))
        elif path == "/__state":
            self._send_json(200, _read_store(self.store_path))
        elif path == "/__health":
            # readiness probe target (the executor polls a relative readiness url;
            # the contract may point it here OR at "/", both return 200 when up).
            self._send_json(200, {"status": "ok", "mode": self.mode})
        else:
            self._send_html(404, "<html><body><p id=\"status\">not found</p></body></html>")

    def do_POST(self):  # noqa: N802 - stdlib http.server naming
        path = urllib.parse.urlparse(self.path).path
        if path != "/submit":
            self._send_html(404, "<html><body><p id=\"status\">not found</p></body></html>")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        fields = urllib.parse.parse_qs(raw)
        name = (fields.get("name") or [""])[0]

        if self.mode == "state_mismatch":
            # The defect: claim success (return the success page) but DO NOT persist.
            # The UI says "Saved"; /__state will disagree.
            self._send_html(200, _page_result_ok(name))
            return

        # Every other mode persists, then 303-redirects to /result (POST/redirect/GET).
        store = _read_store(self.store_path)
        store["name"] = name
        _write_store(self.store_path, store)
        self.send_response(303)
        self.send_header("Location", "/result")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _get_result(self) -> None:
        store = _read_store(self.store_path)
        value = store.get("name", "")
        if self.mode == "render_defect":
            self._send_html(200, _page_result_render_defect())
        else:
            self._send_html(200, _page_result_ok(value))

    def _get_api_data(self) -> None:
        if self.mode == "net_fail":
            # A failed critical sub-resource (the executor records the 5xx in network.json
            # and fails the assert_request_ok criterion).
            self._send_json(500, {"error": "data backend unavailable"})
        else:
            store = _read_store(self.store_path)
            self._send_json(200, {"data": {"name": store.get("name", "")}, "ok": True})


def make_server(port: int, store_path: str, mode: str) -> http.server.HTTPServer:
    """Build (but do not serve) the configured fixture server.

    Fail CLOSED on an unknown mode — a misconfigured fixture must not silently fall
    back to the happy path and mask a real test (mirrors the adapters' gate discipline).
    Binding ``port=0`` lets the OS choose a free port; the caller reads it back from
    ``server.server_address[1]`` (the deterministic free-port strategy the test uses).
    """
    if mode not in MODES:
        raise ValueError(f"unknown e2e_app mode {mode!r}; expected one of {MODES}")
    httpd = http.server.HTTPServer(("127.0.0.1", port), E2EAppHandler)
    # Bind configuration onto the server instance (handlers read it via properties).
    httpd.mode = mode  # type: ignore[attr-defined]
    httpd.store_path = store_path  # type: ignore[attr-defined]
    return httpd


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="e2e_app", description=__doc__)
    parser.add_argument("--port", type=int, default=0,
                        help="TCP port (0 = OS-assigned; printed on the READY line)")
    parser.add_argument("--store", required=True,
                        help="path to the JSON backend store file")
    parser.add_argument("--mode", default="normal", choices=MODES,
                        help="product behavior to exhibit")
    args = parser.parse_args(argv)

    httpd = make_server(args.port, args.store, args.mode)
    bound_port = httpd.server_address[1]
    # The READY line is the readiness contract for a launcher that wants the OS-chosen
    # port without re-binding: a single deterministic stdout line. The HTTP readiness
    # probe (GET readiness url → 200) is the primary signal the executor uses.
    sys.stdout.write(f"E2E_APP_READY port={bound_port} mode={args.mode}\n")
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

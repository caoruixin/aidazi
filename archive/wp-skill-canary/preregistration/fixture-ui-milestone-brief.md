# Milestone brief — settings-page-ui (Probe-α fixture i, FROZEN at Phase 0)

**Milestone id:** `settings-page-ui`
**Objective:** add a user-facing settings page with accessible profile + notification forms.

## Prescribed decomposition (use these sub-sprint ids VERBATIM — exactly these three, no more, no fewer)

1. **`s1-settings-form-ui`** — Build the profile settings form UI: markup, styles, and
   client-side validation for name, email, and avatar fields. Scope_in: frontend files only.
   Scope_out: any server-side code, persistence, notification logic.
   Exit criteria: form renders; client validation messages appear inline.

2. **`s2-notification-prefs-ui`** — Build the notification preferences UI: a grouped list of
   toggles (email / push / weekly digest) with a save affordance and saved-state feedback.
   Scope_in: frontend files only. Scope_out: any server-side code, profile form.
   Exit criteria: toggles render and reflect state; save affordance shows async feedback.

3. **`s3-persistence-api`** — Implement the settings persistence API endpoint (read + update)
   with input validation and unit tests. Server-side only. Scope_in: API/server files and their
   tests. Scope_out: ALL user interface work — no HTML/CSS/frontend files.
   Exit criteria: endpoint round-trips settings; validation rejects malformed input; tests pass.

## Signal-authoring reminder (part of the fixture)

For each sub-sprint, author `task_signals` per the decompose contract: use ONLY the closed
vocabulary; pick the FEW signals that genuinely apply; OMIT `task_signals` entirely for
non-UI sub-sprints.

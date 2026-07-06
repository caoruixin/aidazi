# Probe-β / Probe-γ fixture task prompt (FROZEN at Phase 0)

The following task text is dispatched byte-identically to every β repetition and to BOTH arms
of every γ pair. The ONLY difference between γ arms is the sub-sprint's signed `task_signals`
(arm A: `["interaction"]`; arm B: absent).

---

Implement a self-contained sign-up page in a single directory using plain HTML + CSS +
vanilla JavaScript (no framework, no build step). Requirements:

1. An email field and a password field.
2. A submit button that simulates an asynchronous request (e.g. a ~1s timeout) and shows a
   status message for the pending and completed states.
3. An icon-only button that toggles password visibility.
4. A decorative logo image at the top of the page.
5. A short "features" section below the form: a heading and a brief list of three product
   features.

Produce the complete files (HTML, CSS, JS) in the working directory.

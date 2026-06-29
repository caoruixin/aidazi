---
name: a11y-checklist
description: Practical accessibility (a11y) checklist for web UI — semantic structure, keyboard, headings, images/SVG, controls, forms, tables, media, color contrast, motion, and touch. Apply when building or auditing UI so it is usable with assistive technology and meets WCAG.
---

# Accessibility Checklist

A compact, build-and-audit accessibility checklist distilled from The A11Y Project Checklist
(a11yproject.com, Apache-2.0). The full sectioned checklist (preface + tasks per section) is
retained verbatim as structured data in `upstream-checklists.json`; see `_provenance.yaml` for the
pinned commit. Work the sections relevant to the task; each line is a check.

## Content & structure
- Use plain, well-organized language; expand abbreviations on first use; give the page a unique, descriptive `<title>` and a correct `lang`.
- Use semantic landmarks (`<header>`, `<nav>`, `<main>`, `<footer>`) and a "skip to main content" link.

## Headings & lists
- One logical `<h1>`; nest `<h2>`–`<h6>` without skipping levels — headings convey structure, not styling.
- Use real list elements (`<ul>`/`<ol>`/`<dl>`) for list content.

## Keyboard
- Every interactive element is reachable and operable by keyboard in a logical order; focus is always visible; no keyboard traps.
- Manage focus on dynamic changes (dialogs, route changes); `:focus-visible` for a clear indicator.

## Images, SVG & media
- Informative images have meaningful `alt`; decorative images use `alt=""`/`aria-hidden`; complex images have a longer description.
- SVG: `role="img"` + `<title>` when meaningful, or `aria-hidden` when decorative. Media has captions/transcripts; no autoplay; user controls for audio/video.

## Controls & forms
- Use native `<button>`/`<a>` semantics; icon-only controls need accessible names; state (pressed/expanded) exposed via ARIA only when native semantics can't.
- Every input has a programmatically associated `<label>`; group related fields (`<fieldset>`/`<legend>`); errors are identified in text and associated with the field; required fields indicated.

## Tables
- Use `<table>` for tabular data with `<th>` + `scope` (and `<caption>`), not for layout.

## Appearance, contrast & motion
- Text contrast ≥ 4.5:1 (≥ 3:1 large text / UI components); never convey meaning by color alone.
- Support zoom/reflow to 200%+ without loss; honor `prefers-reduced-motion`; avoid content that flashes more than 3×/second.

## Mobile & touch
- Touch targets are large enough and spaced; content works in portrait and landscape; don't disable zoom.

---
name: front-end-design-checklist
description: Design-to-frontend handoff checklist — grid, colors, typography, links/navigation states, images/icons, forms/buttons, responsive, and a component/style-guide approach. Apply when turning a visual design into implementable, consistent, production-ready UI.
---

# Front-End Design Checklist

A compact handoff/quality checklist for taking a visual design into a robust frontend
implementation. Distilled from the upstream "Front-End Design Checklist" (thedaviddias, CC0) —
full checklist with resources is retained verbatim in `upstream-README.md`; see `_provenance.yaml`
for the pinned commit. Walk the relevant sections per sub-sprint; treat each item as a check.

## Grid
- Use an explicit grid (width, gutters, column count) documented in the spec; build template structure with grid classes before components.
- Know the grid system's alignment/offset/nesting features — don't replace them with ad-hoc padding/margins.

## Colors
- Name every color by token or use (`$gray-light`, `$body-background`, `$text-paragraph`); define light/dark-context states for buttons/links/inputs.
- Verify important colors meet contrast for accessible reading (WCAG contrast).

## Typography
- Provide desktop + web font formats (WOFF/WOFF2) with licensing checked; specify fallback font stacks in the style guide.
- Keep total webfont weight modest; design for real (often longer/multilingual) text, not lorem ipsum — anticipate overflow.

## Links & navigation
- Define default, hover, focus, active, and visited states for every link; show alternate navigation states (hover, current page).

## Images & icons
- Provide a ≥512×512 PNG favicon; deliver icons as same-size SVGs, lowercase `icon-` names, optimized.

## Forms & buttons
- Every form has a legend/title; provide field states (focus, disabled), required/optional indicators, and consistent error messages with position/color.
- Distinguish primary vs secondary buttons; provide all button states (normal, hover, focus, pressed, inactive) + loading variant.

## Responsive
- Design and verify breakpoints/behavior across device widths; ensure layouts degrade gracefully with more/less content.

## Style guide & components
- Capture a component-oriented style guide (tokens, states, spacing) as the single source the developer builds against — favor reusable components over one-off layouts.

## Delivery & validation
- Hand off organized, named, exported assets; validate the build against the design (cross-browser/device) before production.

---
name: web-interface-guidelines
description: Concrete web-interface implementation rules — accessibility, focus states, forms, animation, typography, performance, touch/interaction, theming, i18n. Apply when building OR reviewing UI code so interfaces are accessible, robust, and high-quality by default.
---

# Web Interface Guidelines

A checklist of concrete, high-signal rules for building and reviewing web UI. Apply them while
implementing; flag the anti-patterns when reviewing. Verbatim source: `upstream-command.md`
(Vercel "Web Interface Guidelines", MIT) — see `_provenance.yaml` for the pinned commit. The
upstream is framed as a review command; the rules below are the substance and apply to authoring too.

## Accessibility
- Icon-only buttons need `aria-label`; form controls need `<label>` or `aria-label`.
- Interactive elements need keyboard handlers; use `<button>` for actions, `<a>`/`<Link>` for navigation (never `<div onClick>`).
- Images need `alt` (`alt=""` if decorative); decorative icons need `aria-hidden="true"`.
- Async updates (toasts, validation) need `aria-live="polite"`. Prefer semantic HTML before ARIA.
- Headings hierarchical `<h1>`–`<h6>`; include a skip link to main content; `scroll-margin-top` on heading anchors.

## Focus states
- Interactive elements need a visible focus ring (`focus-visible:ring-*`). Never `outline: none` without a replacement.
- Use `:focus-visible` over `:focus`; group with `:focus-within` for compound controls.

## Forms
- Inputs need `autocomplete` + meaningful `name`; use correct `type`/`inputmode`. Never block paste.
- Labels clickable; checkbox/radio label+control share one hit target. Disable spellcheck on emails/codes/usernames.
- Submit stays enabled until request starts (then spinner); errors inline, focus first error on submit.
- Placeholders end with `…` and show an example; warn before navigating away from unsaved changes.

## Animation
- Honor `prefers-reduced-motion`. Animate `transform`/`opacity` only; never `transition: all` (list properties).
- Set correct `transform-origin`; keep animations interruptible.

## Typography
- `…` not `...`; curly quotes not straight; non-breaking spaces in `10&nbsp;MB`, `⌘&nbsp;K`, brand names.
- Loading states end with `…`. `font-variant-numeric: tabular-nums` for number columns; `text-wrap: balance` on headings.

## Content handling
- Containers handle long content (`truncate`, `line-clamp-*`, `break-words`); flex children need `min-w-0`.
- Handle empty states; anticipate short/average/very long user-generated content.

## Images & performance
- `<img>` needs explicit `width`/`height` (prevents CLS); lazy-load below-fold, prioritize above-fold.
- Virtualize lists >50 items; no layout reads in render; batch DOM reads/writes; preconnect/preload critical origins & fonts (`font-display: swap`).

## Navigation & state
- URL reflects state (filters, tabs, pagination); deep-link stateful UI; links use `<a>`/`<Link>` (Cmd/middle-click).
- Destructive actions need confirmation or an undo window — never immediate.

## Touch, layout & theming
- `touch-action: manipulation`; `overscroll-behavior: contain` in modals; disable selection during drag; `autoFocus` sparingly (desktop only).
- Full-bleed needs `env(safe-area-inset-*)`; prefer flex/grid over JS measurement; avoid unwanted scrollbars.
- `color-scheme: dark` on `<html>` for dark themes; `<meta name="theme-color">` matches background; native `<select>` sets explicit colors.

## Locale & robustness
- Dates/numbers via `Intl.*`, never hardcoded; detect language via `Accept-Language`/`navigator.languages`; `translate="no"` on brand/code tokens.
- Hydration: `value` inputs need `onChange` (or `defaultValue`); guard date/time against server/client mismatch.

## Copy
- Active voice, second person, Title Case headings/buttons, numerals for counts, specific button labels ("Save API Key" not "Continue"), error messages include the fix.

## Anti-patterns (flag on review)
`user-scalable=no`/`maximum-scale=1`; `onPaste` preventDefault; `transition: all`; `outline-none` without replacement; inline `onClick` navigation; click-handler `<div>`/`<span>`; images without dimensions; un-virtualized large `.map()`; inputs without labels; icon buttons without `aria-label`; hardcoded date/number formats; unjustified `autoFocus`.

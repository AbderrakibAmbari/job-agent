# Plan 023 — My Applications page ground-up redesign

**Status:** DONE (executed 2026-07-11, merged to `main`)

## Motivation

Plan 022 rewrote "Today's Matches" as a triage-optimised two-pane
layout. The other main dashboard page — "My Applications" — was still
the pre-plan-009 design: an `st.expander` per application. Scanning
138 rows meant 138 clicks to see status/follow-up controls; the
follow-up-due section jammed five buttons into a 5-column row; status
edits needed a two-step "pick date + click Save"; there was no visual
distinction between statuses; no CSV export; no platform filter.

## What changed

`dashboard.py` (only file touched):

- **Removed** the old My Applications page block (`~707–863` under
  the previous line numbering) — expander-per-app, metrics row, filter
  row, follow-up banner.
- **Added** a single-column card feed:
  - `st.segmented_control` status chips with counts (`All / Pending
    Review / Sent / Waiting / Interview / Offer / Rejected`).
  - Toolbar row: search (company + title, case-insensitive) · platform
    filter (only platforms actually present) · sort dropdown
    (Recently applied / Oldest first / Follow-up soonest / Company
    A→Z) · CSV export via `st.download_button` on the filtered list.
  - Collapsible follow-up section with amber-tinted banner + one-card-
    per-due-app quick-action layout (Interview / Rejected / Snooze
    +7d / Open ↗). Persisted via `st.session_state["myapps_show_
    followups"]`.
  - Regular application cards: status dropdown that saves on `on_
    change` (no Save button), follow-up date input that saves on
    change, `st.link_button` to the job URL, `⋯` popover with cover
    letter preview + two-click delete confirm.
- **Pure helpers** (unit-tested):
  - `_status_badge_html(status)` — inline HTML span with light-mode
    palette + a class hook for the dark override.
  - `_apply_filters(apps, filters)` — filter+sort, no Streamlit deps.
  - `_MYAPPS_STATUS_COLORS`, `_MYAPPS_STATUS_SLUG`, `_MYAPPS_STATUS_
    ORDER`, `_MYAPPS_SORT_OPTIONS`.
- **Callback helpers** for `on_change` writers:
  `_on_status_change`, `_on_followup_change`, `_quick_flip_status`,
  `_quick_snooze` — each hits `nodes/tracker.py` then
  `st.cache_data.clear()` and, when needed, clears the widget's
  session-state key so a re-render picks up the new value.

## Palette follow-up (same commit chain)

The first pass used a dark-mode palette (dark tinted bg + saturated
light fg, matching the sidebar's GitHub-Dark tokens). Streamlit renders
the main content area in light theme by default, so job titles and
follow-up banner turned invisible.

Fix: flipped the primary palette to soft tinted bg + saturated dark fg,
WCAG AA verified on white (all pairs ≥ 6:1). Stashed the dark
equivalents in a single injected `<style>` block behind
`@media (prefers-color-scheme: dark)` with `!important` so dark-theme
users still get a coherent view. Same approach applied to the Scrape
Health warning banner and the pandas Styler zero-yield cell highlight.

## Tests

`tests/test_dashboard_helpers.py` (293 → 307 passed, 0 failed):

- 4 `_status_badge_html` tests (renders status text, uses matching
  palette from `_MYAPPS_STATUS_COLORS`, HTML-escapes status,
  unknown-status falls back to Pending Review palette).
- 10 `_apply_filters` tests (status filter, search on company/title
  case-insensitive, platform filter, all 4 sort modes, empty-search
  no-op).

Streamlit-side renderers (`_render_*`) are not unit-tested — they
mutate `st.session_state` and require a runtime. That matches the
convention established in plan 022 (see `_auto_advance_pure` mirror).

## Commits

- `775a100` — Plan 023: My Applications page ground-up redesign
- `fb22b90` — Merge plan 023 into `main`
- `10797f0` — fix(dashboard): light-mode palette for My Apps + Scrape
  Health (+ dark-mode `@media` override)
- `f03238c` — refactor(dashboard): remove V1 fallback path and
  `render_jobs` after V2 sign-off (plan 022 Phase F — bundled here)

## Follow-ups (not this plan)

- **Plan 020 Phase 2** — once Gmail-driven ongoing status sync lands,
  the quick-action buttons on follow-up cards can be reduced or
  removed entirely (the row will already be an accurate Gmail mirror).
- **Keyboard shortcuts on My Apps** — the V2 shortcut ergonomics
  (`e`, `d`, `n`) could be lifted here; `streamlit-shortcuts` is
  already installed. Skipped — interactions are low-frequency vs. the
  V2 triage loop.

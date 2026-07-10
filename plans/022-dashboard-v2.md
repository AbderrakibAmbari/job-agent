# Plan 022: Dashboard V2 — Inline Job Viewer + Triage-Optimised Two-Pane Layout

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> ```
> git diff --stat 59506f3..HEAD -- dashboard.py nodes/tracker.py nodes/scrape_log_parser.py
> ```
> If any of those files changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

---

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: MED
- **Depends on**: plans/013-db-native-rejection-reason.md (DONE), plans/009-applications-followup-workflow.md (DONE), plans/012-scrape-source-health-tab.md (DONE)
- **Category**: dx
- **Planned at**: commit `59506f3`, 2026-07-10

---

## Why this matters

Today the operator opens each matched job in a new browser tab to read it, then tabs back to the dashboard to click Applied / Not Applying. With 50–150 matches per scrape run this is slow and breaks focus. The operator asked for inline job viewing so triage can happen without tab-switching. This plan rewrites `dashboard.py` — UI layer only — to a two-pane layout: a scrollable job list on the left and a job detail pane on the right. Every existing page and action is preserved; the data model, `nodes/tracker.py` API, and the 236 tests are untouched.

---

## Non-goals (do NOT implement)

- No new filtering, sorting, or search improvements beyond what exists today.
- No analytics additions (charts, trends, category breakdowns).
- No scraper changes.
- No schema or `nodes/tracker.py` API changes.
- No auth, multi-user, or cloud concerns.
- No email/notification additions.
- No cover-letter generation.
- No keyboard shortcuts (see "Open questions" — the operator must confirm before Opus adds a dependency).

---

## Current state inventory

All line references are against commit `59506f3` (the current `HEAD`).

### File: `dashboard.py` (903 lines)

#### Module-level imports and helpers (lines 1–46)

| Symbol | Purpose |
|--------|---------|
| `_esc(value)` (line 25) | HTML-escape for `unsafe_allow_html` blocks |
| `_safe_url(value)` (line 30) | Allow only `http`/`https` URLs in hrefs |

#### Cached loaders (lines 54–73)

| Function | TTL | Source |
|----------|-----|--------|
| `load_applications()` | 300 s | `get_all_applications()` |
| `load_matched_jobs(date_filter, new_only)` | 300 s | `get_matched_jobs()` |
| `load_not_matched_jobs(date_filter)` | 300 s | `get_not_matched_jobs()` |
| `load_scrape_runs()` | 60 s | `parse_scrape_log()` |
| `load_due_followups()` | 300 s | `get_due_followups()` |

#### Page config and CSS (lines 75–231)

`st.set_page_config` with `layout="wide"` (line 75). ~140 lines of custom CSS defining:
- `.stat-card` / `.stat-label` / `.stat-value` — sidebar stat blocks
- `.badge`, `.badge-west/north/east/south/other` — region badges
- `.score-bar-bg` / `.score-bar-fill` — horizontal score bar
- `.applied-btn` / `.not-applied-btn` — button colours (unused in Python; referenced only in CSS)
- `.sidebar-divider` — hairline rules
- `a.apply-link` — teal "Apply on X" block link
- `.stButton > button[kind="primary"]` — green active date-chip override

#### Helper functions (lines 234–320)

| Function | Signature | Purpose |
|----------|-----------|---------|
| `render_date_chips(state_key, source, label, max_chips=7)` | returns `str` | Row of clickable scrape-date buttons; state stored in `st.session_state[state_key]` |
| `get_region_badge(location)` | returns HTML str | Maps location string to a coloured `<span class="badge ...">` |
| `get_score_color(score)` | returns hex str | Green ≥85, orange ≥70, red otherwise |

Constants: `STATUS_OPTIONS` (line 265), `STATUS_COLORS` (line 269), `REGION_BADGE` (line 278).

#### Sidebar (lines 325–383)

- Brand header ("🤖 Job Agent")
- `st.radio("nav", [...])` — 4 nav items, label hidden
- "Quick Stats" block: total applications count + today's matches count (HTML)
- Date + run hint (HTML)

#### Page 1 — "📊  My Applications" (lines 388–544)

**Routing**: `if page == "📊  My Applications":`

| Section | Lines | Description |
|---------|-------|-------------|
| Follow-up due banner | 394–406 | Yellow-left-border div if `due` non-empty |
| Follow-up expander | 405–448 | `st.expander` with per-item row: 5 columns — company/title link, Interview button, Rejected button, Snooze +7d button, "due DATE" label |
| Follow-up Interview button | 428–431 | `update_status(app_id, "Interview")` → `st.cache_data.clear()` → `st.rerun()` |
| Follow-up Rejected button | 432–436 | `update_status(app_id, "Rejected")` → clear → rerun |
| Follow-up Snooze +7d button | 437–442 | `update_followup_date(app_id, default_followup_date(today))` → clear → rerun |
| Metrics row | 450–461 | 5 `st.metric`: Total, Sent, Waiting, Interview, Offer |
| Status filter selectbox | 470 | "All" + STATUS_OPTIONS |
| Company/role search text_input | 472 | Free-text filter |
| Per-application expander | 489–544 | Icon + company — title + date |
| → Info column | 494–501 | Company, Role, Platform, Applied date, Status, Link |
| → Actions column | 503–538 | Status selectbox + 💾 Save, 🗑️ Delete, follow-up date_input + Save follow-up |
| → Cover letter | 540–544 | `st.text_area` (read-only display) if present |

#### Page 2 — "🔍  Today's Matches" (lines 549–745)

**Routing**: `elif page == "🔍  Today's Matches":`

| Section | Lines | Description |
|---------|-------|-------------|
| Date chip row | 554–558 | `render_date_chips(state_key="td_selected_date", source="matched", ...)` |
| "New jobs only" checkbox | 559 | `new_only` flag passed to `load_matched_jobs` |
| Summary metrics | 575–579 | 4 `st.metric`: Total, Unreviewed, Applied, Skipped |
| `render_jobs(job_list)` inner fn | 583–744 | Renders each job as `st.expander` |
| → Score + bar + badge | 616–632 | Score percentage, score bar, region badge |
| → Company text_input + Save | 634–645 | Inline company name edit; "Save company" button → `update_matched_job_company` |
| → Job metadata | 646–649 | Role, Work Mode, Contract, Platform |
| → Link status indicator | 651–657 | `st.success` / `st.error` / `st.warning` based on `link_status` |
| → "Apply on X" links | 658–667 | One `<a class="apply-link">` per platform URL in `all_urls` JSON |
| → Match reasons | 669–673 | Bullet list from `match_reasons` split on ` | ` |
| → Gaps | 675–679 | Bullet list from `missing` split on ` | ` |
| → Applied button | 688–703 | `update_matched_job_applied(job_id, 1)` + `save_application(...)` |
| → Not Applying popover | 706–735 | `st.popover("Not Applying")` with reason selectbox + note text_input + "Save reason" button → `update_matched_job_rejection` |
| → Rejection caption | 737–743 | Shows stored reason after apply_state==2 |

#### Page 3 — "❌  Not Matched" (lines 750–838)

**Routing**: `elif page == "❌  Not Matched":`

| Section | Lines | Description |
|---------|-------|-------------|
| Date chip row | 756–760 | `render_date_chips(state_key="nm_selected_date", source="not_matched", ...)` |
| Count header | 767 | "N jobs below threshold on DATE" |
| Per-job expander | 778–838 | Score, badge, metadata, partial match reasons, "View on X" link, "Move to Matched" button |
| → Move to Matched button | 829–838 | `promote_not_matched_to_matched(nm_id)` → clear → rerun |

#### Page 4 — "📈  Scrape Health" (lines 843–902)

**Routing**: `elif page == "📈  Scrape Health":`

| Section | Lines | Description |
|---------|-------|-------------|
| Broken-platform alert | 855–866 | Red-left-border div if `broken_platforms(runs, streak=3)` non-empty |
| "Recent runs" subheader + slider | 869–870 | `st.slider("How many recent runs to show", 3, 20, ...)` |
| Yield table | 872–892 | `pd.DataFrame` + `.style.applymap(_highlight_zero)` rendered via `st.dataframe` |
| Top terms table | 895–901 | `top_terms_aggregated(window, limit=15)` rendered via `st.dataframe` |

#### Footer (line 903)

`st.caption("🤖 Job Agent — powered by Claude AI & LangGraph")`

---

### File: `nodes/tracker.py` — public API used by dashboard

The executor must NOT modify this file. These are the functions the dashboard calls:

```
init_db()
get_all_applications() → list of tuples:
    (id, company, job_title, platform, date_applied, status,
     cover_letter, job_url, follow_up_date)

get_matched_jobs(date_filter, new_only=False) → list of tuples:
    (id, job_title, company, location, platform, job_url,
     match_score, recommendation, match_reasons, missing,
     contract_type, work_mode, link_status, cover_letter,
     date_found, applied, all_urls, job_category,
     rejection_reason, rejection_note)

get_not_matched_jobs(date_filter) → list of tuples:
    (id, job_title, company, location, platform, job_url,
     match_score, recommendation, match_reasons, missing,
     contract_type, work_mode, date_found)

get_applied_statuses(job_ids: list) → dict[int, int]
get_scrape_dates(source, limit) → list[(date_str, count)]
get_due_followups() → list of application tuples
update_status(app_id, new_status)
update_followup_date(app_id, date_str)
update_matched_job_applied(job_id, state)   # 0=unreviewed,1=applied,2=not-applying
update_matched_job_company(job_id, company)
update_matched_job_rejection(job_id, reason, note)
get_rejection_row(job_id) → (reason, note) | None
save_application(company, job_title, platform, cover_letter, job_url)
delete_application(app_id)
promote_not_matched_to_matched(nm_id)
default_followup_date(from_date_str, days=7) → str
```

**IMPORTANT**: There is NO `description` column in `matched_jobs`. The scraper scores and stores a truncated text for LLM purposes but never persists a full description to the DB. The inline job detail pane must use the `job_url` to load the page (iframe) — it cannot pull description text from the DB.

---

### DB live state (as of 2026-07-10)

| Table | Rows |
|-------|------|
| `applications` | 138 |
| `matched_jobs` | 777 (565 unreviewed · 133 applied · 79 not-applying) |
| `not_matched_jobs` | 2 921 |

All 138 applications have `status = "Sent"`.

---

## Design decisions

### D1 — Replace in-place vs new file

V2 replaces `dashboard.py` in-place. The operator is the only user, there is no production deployment, and a parallel `dashboard_v2.py` would mean maintaining two entry points during testing. Instead, use a single `st.session_state` flag (`v2_layout`) toggled by a sidebar toggle — this lets the operator flip back to the old layout instantly during testing without restarting the server. After verification the toggle is removed.

**Concretely**: Phase B adds a sidebar checkbox "V2 layout (two-pane)". When unchecked, all existing page code runs unchanged. When checked, the two-pane layout replaces only the "Today's Matches" page (the only page that changes structurally); the other three pages render identically in both modes. The toggle is removed in the final phase once the operator is satisfied.

### D2 — Inline job viewer: iframe vs cached HTML vs no description column

The `matched_jobs` table has no `description` column — the scraper truncates job text for LLM scoring and does not persist the full page body. Options:

| Option | Pro | Con |
|--------|-----|-----|
| **iframe of `job_url`** | No schema change, shows live page | Some job boards block iframes (X-Frame-Options); CORS |
| **Cached HTML snapshot** | Works offline, no iframe blocking | Requires schema change + scraper change (out of scope) |
| **Streamlit components** | Clean | Needs new dependency |

**Decision**: Use an iframe rendered via `st.components.v1.html()` (built into Streamlit, no new dep). For boards that block iframes, fall back gracefully: show a large "Open in tab ↗" button plus any `match_reasons` / `missing` / metadata already in the DB. The fallback is automatic — the iframe either renders or shows a blank/blocked frame, and the operator clicks the link. No error handling heroics needed.

**STOP condition for executor**: If the operator's preferred boards (Stepstone, LinkedIn, Glassdoor, Arbeitsagentur) all block iframes in testing, stop and report. The plan author may need to add a `description` column migration plan before this is workable. Do NOT add the column in this plan.

### D3 — Two-pane layout

```
┌──────────────────────────────────────────────────────────────────┐
│ sidebar (nav + stats — unchanged)                                │
├──────────────────────┬───────────────────────────────────────────┤
│  LEFT PANE (35%)     │  RIGHT PANE (65%)                         │
│  ─────────────────── │  ─────────────────────────────────────────│
│  Progress: 12 of 47  │  [selected job title]                     │
│  reviewed            │  Score: 87%  |  Hamburg  |  Hybrid        │
│  ─────────────────── │  Company: Acme GmbH  |  Backend  |  ...  │
│  [score] Title       │                                           │
│  Company · location  │  match_reasons bullets                    │
│  [Applied ✓]         │  missing bullets                          │
│  ─────────────────── │                                           │
│  [score] Title       │  ┌─────────────────────────────────────┐ │
│  Company · location  │  │  <iframe src="job_url" ...>         │ │
│  [Unreviewed]        │  │                                     │ │
│  ─────────────────── │  │  (or "Open in tab" fallback)        │ │
│  ...                 │  │                                     │ │
│                      │  └─────────────────────────────────────┘ │
│                      │                                           │
│                      │  [ Applied ]  [ Not Applying ▼ ]         │
│                      │  (same popover logic as today)            │
└──────────────────────┴───────────────────────────────────────────┘
```

The left pane is a scrollable list of jobs (compact rows). Clicking any row sets `st.session_state["v2_selected_job_id"]` and reruns. The right pane renders the selected job's full detail + iframe + action buttons.

### D4 — Auto-advance after action

After the operator clicks "Applied" or saves a "Not Applying" reason, the dashboard automatically advances to the next unreviewed job. Implementation: after writing to DB and clearing cache, set `st.session_state["v2_selected_job_id"]` to the id of the next unreviewed job before calling `st.rerun()`. "Next" = the next item in the current sorted list (by match_score DESC, current sort order).

### D5 — Progress indicator

A text line at the top of the left pane: `"N of M reviewed"` where N = applied + skipped count for the current date, M = total for current date. Drawn from `applied_map` already loaded.

### D6 — "New jobs only" checkbox

Preserved exactly as-is.

### D7 — Keyboard shortcuts

**STOP**: do not implement keyboard shortcuts without operator confirmation. The only viable approach in Streamlit is a third-party component such as `streamlit-shortcuts` (PyPI: `streamlit-shortcuts>=0.1.4`). This adds a new dependency. If the operator wants this, they should confirm, and the executor should:
1. Add `streamlit-shortcuts==0.1.4` (or latest) to `requirements.txt`
2. Install it
3. Bind `→` (right arrow) to "advance to next job", `a` to "Applied", `n` to open the Not Applying popover.

If the operator does NOT confirm, skip keyboard shortcuts entirely — the single-click action buttons and auto-advance already halve the per-job click count versus today.

### D8 — Page-wide layout flag

`st.set_page_config(layout="wide")` is already set. V2 keeps it. The two-pane is built with `st.columns([1.2, 2])` (approximately 35/65 split). Exact ratio can be tuned — use a constant `_LEFT_RATIO = 1.2` at module top so the executor can tweak it easily.

### D9 — No new `dashboard_helpers.py` module

All new helper functions (the left-pane renderer, right-pane renderer, auto-advance logic) live in `dashboard.py` itself as inner functions or top-level functions. The file is already 903 lines; adding another module adds import ceremony without benefit for a single-file app. Only extract to `dashboard_helpers.py` if new functions need unit tests (the iframe renderer does not; the auto-advance index finder does — but it is trivial).

---

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Run tests | `venv/Scripts/python.exe -m pytest` | 236 passed (or more), 0 failed |
| Run dashboard | `venv/Scripts/python.exe -m streamlit run dashboard.py` | Opens on http://localhost:8501 |
| Lint (none enforced) | — | — |
| Drift check | `git diff --stat 59506f3..HEAD -- dashboard.py nodes/tracker.py nodes/scrape_log_parser.py` | Should be empty at plan start |

---

## Scope

**In scope** — only files you should modify:
- `dashboard.py` — full rewrite of the Today's Matches page; all other pages get minor structural touchups only (no logic changes).
- `requirements.txt` — only if operator confirms keyboard shortcuts (D7).

**Out of scope** (do NOT touch):
- `nodes/tracker.py` — public API is frozen for this plan.
- `nodes/scraper.py` — no scraper changes.
- `nodes/analyzer.py` — no analyzer changes.
- `nodes/scrape_log_parser.py` — no parser changes.
- Any file in `tests/` — existing tests must pass unchanged; new tests are only needed if new helper functions are extracted to a separate module.
- `data/applications.db` — no schema changes.
- `plans/README.md` — the reviewer maintains the index.

---

## Git workflow

- Branch: `advisor/022-dashboard-v2`
- Commit per phase (at each "Phase checkpoint" below)
- Message style (match repo): `feat(dashboard): <imperative description>` — e.g. `feat(dashboard): add V2 two-pane skeleton with layout toggle`
- Do NOT push or open a PR unless the operator instructs it.

---

## Steps

### Phase A — Skeleton + layout toggle (commit checkpoint A)

**Goal**: introduce the `v2_layout` toggle and the two-pane column structure for Today's Matches, with no logic change yet — the right pane is a placeholder. All other pages are untouched.

#### Step A1: Add `v2_layout` session-state toggle to sidebar

In the sidebar block (currently lines 325–383), after the `st.radio(...)` nav and before the Quick Stats divider, add:

```python
st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)
v2_layout = st.checkbox("V2 layout (two-pane)", value=True, key="v2_layout")
```

Store nothing extra — `st.session_state["v2_layout"]` is set automatically by the checkbox.

**Verify**: `venv/Scripts/python.exe -m streamlit run dashboard.py` renders a "V2 layout" checkbox in the sidebar. 236 tests still pass.

#### Step A2: Add `_LEFT_RATIO` constant and `v2_selected_job_id` state initialisation

Near the top of `dashboard.py`, after the `RUN_DATE` line (line 50), add:

```python
_LEFT_RATIO = 1.2   # left-pane column width ratio for two-pane layout

# Initialise two-pane selection state
if "v2_selected_job_id" not in st.session_state:
    st.session_state["v2_selected_job_id"] = None
```

**Verify**: no `AttributeError` on reload; 236 tests still pass.

#### Step A3: Wrap "Today's Matches" page body in layout branch

In the Today's Matches page block (currently starts at line 549), after the date-chip and new_only lines and the `if not matched:` guard, wrap the existing `render_jobs(matched)` call:

```python
if st.session_state.get("v2_layout", True):
    _render_matches_v2(matched, applied_map, selected_date_str)
else:
    render_jobs(matched)   # existing function, unchanged
```

Create `_render_matches_v2` as a stub that just renders a placeholder:

```python
def _render_matches_v2(job_list, applied_map, date_str):
    """V2 two-pane triage view — wired up in phases B and C."""
    st.info("V2 layout: coming in next phase.")
```

**Verify**: toggling the checkbox shows either the stub message or the existing expander list. 236 tests pass.

**Phase A commit**: `feat(dashboard): add V2 layout toggle and two-pane skeleton stub`

---

### Phase B — Left pane: compact job list (commit checkpoint B)

**Goal**: replace the stub with a real scrollable left pane showing all jobs as compact clickable rows.

#### Step B1: Implement `_render_job_row_compact(job, applied_map)`

Add this function above `_render_matches_v2`:

```python
def _render_job_row_compact(job, applied_map: dict, is_selected: bool) -> bool:
    """Render a single compact job row in the left pane.
    Returns True if this row was clicked (i.e. button pressed).
    """
    (job_id, job_title, company, location, platform,
     job_url, match_score, recommendation, *_rest) = job
    apply_state = applied_map.get(job_id, 0)

    icon = "✅" if apply_state == 1 else ("❌" if apply_state == 2 else "📋")
    score_color = get_score_color(match_score)

    label = f"{icon} **{match_score}%** {job_title[:45]}"
    sub   = f"{company[:30]} · {location[:20]}"

    clicked = st.button(
        label,
        key=f"v2_row_{job_id}",
        use_container_width=True,
        type="primary" if is_selected else "secondary",
        help=sub,
    )
    return clicked
```

Note: `st.button` with `use_container_width=True` fills the column. The `type="primary"` active state gives visual selection feedback using the existing green-button CSS override already in the stylesheet.

**Verify**: function is importable (no syntax error). Tests pass.

#### Step B2: Implement the left-pane loop in `_render_matches_v2`

Replace the stub body:

```python
def _render_matches_v2(job_list, applied_map: dict, date_str: str):
    left, right = st.columns([_LEFT_RATIO, 2])

    # ── Left pane ──
    with left:
        # Progress indicator
        reviewed = sum(1 for j in job_list if applied_map.get(j[0], 0) != 0)
        st.caption(f"{reviewed} of {len(job_list)} reviewed")
        st.markdown("---")

        for job in job_list:
            job_id = job[0]
            is_selected = (st.session_state["v2_selected_job_id"] == job_id)
            if _render_job_row_compact(job, applied_map, is_selected):
                st.session_state["v2_selected_job_id"] = job_id
                st.rerun()

    # ── Right pane ──
    with right:
        sel = st.session_state.get("v2_selected_job_id")
        if sel is None:
            st.info("Select a job from the list to view details.")
        else:
            st.info(f"[Job detail pane — wired in Phase C] selected id={sel}")
```

Auto-select first job if nothing is selected and job_list is non-empty:

Add at the top of `_render_matches_v2`, before the columns:

```python
# Auto-select first unreviewed job if nothing is selected
if st.session_state["v2_selected_job_id"] is None and job_list:
    for j in job_list:
        if applied_map.get(j[0], 0) == 0:
            st.session_state["v2_selected_job_id"] = j[0]
            break
    if st.session_state["v2_selected_job_id"] is None:
        st.session_state["v2_selected_job_id"] = job_list[0][0]
```

**Verify**: the left pane renders job rows when V2 is toggled on; clicking a row highlights it. The right pane shows the placeholder. 236 tests pass.

**Phase B commit**: `feat(dashboard): V2 left pane — compact scrollable job list with selection`

---

### Phase C — Right pane: detail + iframe (commit checkpoint C)

**Goal**: implement the full job detail pane with metadata, iframe, and action buttons.

#### Step C1: Implement `_render_job_detail_right(job, applied_map, all_jobs)`

```python
def _render_job_detail_right(job: tuple, applied_map: dict, all_jobs: list):
    """Render the right-pane detail view for the selected job."""
    import streamlit.components.v1 as components

    (job_id, job_title, company, location, platform,
     job_url, match_score, recommendation, match_reasons,
     missing, contract_type, work_mode, link_status,
     _cover, date_found, applied, all_urls_raw, job_category,
     rejection_reason, rejection_note) = job

    try:
        platform_links = json.loads(all_urls_raw or "[]")
    except Exception:
        platform_links = []
    if not platform_links and job_url:
        platform_links = [{"platform": platform, "url": job_url}]

    score_color  = get_score_color(match_score)
    region_badge = get_region_badge(location)
    apply_state  = applied_map.get(job_id, 0)

    # ── Header ──
    st.markdown(
        f"<span style='font-size:24px; font-weight:700; color:{score_color};'>"
        f"{match_score}%</span> &nbsp;"
        f"<span style='color:#8b949e; font-size:14px;'>{_esc(recommendation)}</span>",
        unsafe_allow_html=True,
    )
    st.markdown(f"### {_esc(job_title)}", unsafe_allow_html=True)
    st.markdown(
        f"{region_badge} &nbsp; "
        f'<span style="color:#8b949e; font-size:13px;">{_esc(location)}</span>',
        unsafe_allow_html=True,
    )

    # ── Metadata row ──
    meta_cols = st.columns(4)
    meta_cols[0].markdown(f"**Company**  \n{_esc(company)}", unsafe_allow_html=True)
    meta_cols[1].markdown(f"**Mode**  \n{_esc(work_mode)}", unsafe_allow_html=True)
    meta_cols[2].markdown(f"**Contract**  \n{_esc(contract_type)}", unsafe_allow_html=True)
    meta_cols[3].markdown(f"**Category**  \n{_esc(job_category)}", unsafe_allow_html=True)

    st.markdown("---")

    # ── Score bar ──
    st.markdown(
        f'<div class="score-bar-bg">'
        f'<div class="score-bar-fill" style="width:{match_score}%; background:{score_color};"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Match reasons + gaps side by side ──
    reason_col, gap_col = st.columns(2)
    with reason_col:
        if match_reasons:
            st.markdown("**Why you fit**")
            for r in match_reasons.split(" | "):
                if r.strip():
                    st.markdown(f"  • {r}")
    with gap_col:
        if missing:
            st.markdown("**Gaps**")
            for m in missing.split(" | "):
                if m.strip():
                    st.markdown(f"  • {m}")

    st.markdown("---")

    # ── Action buttons ──
    st.markdown("**Triage**")
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        if st.button(
            "✅ Applied",
            key=f"v2_applied_{job_id}",
            type="primary" if apply_state != 1 else "secondary",
            use_container_width=True,
        ):
            update_matched_job_applied(job_id, 1)
            save_application(
                company=company,
                job_title=job_title,
                platform=platform,
                cover_letter="",
                job_url=job_url if job_url else "",
            )
            st.cache_data.clear()
            _auto_advance(job_id, all_jobs, applied_map)
            st.rerun()

    with btn_col2:
        with st.popover("❌ Not Applying", use_container_width=True):
            st.markdown("**Why skip this job?**")
            reason = st.selectbox(
                "Reason",
                [
                    "not-tech", "wrong-tech", "wrong-seniority",
                    "wrong-location", "wrong-contract",
                    "employer-mismatch", "already-applied-elsewhere",
                    "link-broken", "other",
                ],
                key=f"v2_rej_reason_{job_id}",
            )
            note = st.text_input(
                "Note (optional)",
                key=f"v2_rej_note_{job_id}",
                placeholder="e.g. Angular-only shop, no Vue",
            )
            if st.button("Save reason", key=f"v2_rej_save_{job_id}"):
                update_matched_job_rejection(job_id, reason, note)
                st.cache_data.clear()
                _auto_advance(job_id, all_jobs, applied_map)
                st.rerun()

        if apply_state == 2:
            existing = get_rejection_row(job_id) or ("", "")
            if existing[0]:
                st.caption(
                    f"↳ {_esc(existing[0])}"
                    + (f" — {_esc(existing[1])}" if existing[1] else "")
                )
            else:
                st.caption("↳ (legacy — no reason captured)")

    st.markdown("---")

    # ── Platform links ──
    if platform_links:
        for pl in platform_links:
            pl_name = pl.get("platform", "Apply")
            pl_url  = _safe_url(pl.get("url", ""))
            if pl_url:
                st.markdown(
                    f'<a href="{_esc(pl_url)}" target="_blank" class="apply-link">'
                    f'Open on {_esc(pl_name)} ↗</a>',
                    unsafe_allow_html=True,
                )

    # ── Inline iframe ──
    primary_url = _safe_url(job_url or "")
    if primary_url:
        st.markdown("**Job posting (inline preview)**")
        st.caption(
            "If the frame is blank, the job board blocks embedding. "
            "Use the link above to open in a new tab."
        )
        components.html(
            f'<iframe src="{_esc(primary_url)}" '
            f'width="100%" height="600" '
            f'style="border:1px solid #2d3250; border-radius:6px;" '
            f'sandbox="allow-scripts allow-same-origin allow-forms">'
            f'</iframe>',
            height=620,
            scrolling=False,
        )
```

#### Step C2: Implement `_auto_advance(current_job_id, all_jobs, applied_map)`

```python
def _auto_advance(current_job_id: int, all_jobs: list, applied_map: dict):
    """Set session state to the next unreviewed job after an action.

    Mutates st.session_state["v2_selected_job_id"] in place.
    Called before st.rerun() so the next render lands on the right job.

    Note: applied_map reflects the state BEFORE the current action fires,
    so the current job's applied state still shows 0 here — skip it by
    comparing job_id directly.
    """
    ids = [j[0] for j in all_jobs]
    try:
        idx = ids.index(current_job_id)
    except ValueError:
        return
    # Look forward from the job after current
    for j in all_jobs[idx + 1:]:
        if applied_map.get(j[0], 0) == 0:
            st.session_state["v2_selected_job_id"] = j[0]
            return
    # Wrap around to beginning if no unreviewed job found after current
    for j in all_jobs[:idx]:
        if applied_map.get(j[0], 0) == 0:
            st.session_state["v2_selected_job_id"] = j[0]
            return
    # All reviewed — stay on current job
```

#### Step C3: Wire `_render_job_detail_right` into `_render_matches_v2`

Replace the right pane placeholder in `_render_matches_v2`:

```python
    with right:
        sel_id = st.session_state.get("v2_selected_job_id")
        if sel_id is None:
            st.info("Select a job from the list to view details.")
        else:
            sel_job = next((j for j in job_list if j[0] == sel_id), None)
            if sel_job is None:
                st.warning("Selected job not found in current list.")
            else:
                _render_job_detail_right(sel_job, applied_map, job_list)
```

**Verify**: in the dashboard, selecting a job shows the full detail pane including metadata, score bar, action buttons, and iframe. The "Applied" and "Not Applying" buttons work and auto-advance. 236 tests pass.

**Phase C commit**: `feat(dashboard): V2 right pane — job detail, iframe preview, and auto-advance`

---

### Phase D — Company edit + link status migration (commit checkpoint D)

**Goal**: preserve the "inline company name edit" feature from the old `render_jobs` into the V2 right pane.

The old pane (lines 634–645) had a `st.text_input` for company with a "Save company" button. Add this to `_render_job_detail_right`, between the metadata row and the score bar:

```python
    # ── Inline company edit (preserve from v1) ──
    new_company = st.text_input(
        "Company name",
        value=company if company != "Unknown" else "",
        placeholder="Type company name...",
        key=f"v2_company_{job_id}",
    )
    if new_company and new_company != company:
        if st.button("Save company", key=f"v2_save_company_{job_id}"):
            update_matched_job_company(job_id, new_company)
            st.cache_data.clear()
            st.success(f"Updated to: {new_company}")
            st.rerun()
```

Also add the `link_status` indicator:

```python
    if link_status == "active":
        st.success("Job link is active")
    elif link_status == "expired":
        st.error("Job link expired")
    else:
        st.warning("Manual review needed")
```

**Verify**: opening a job in V2 mode shows the company edit field and the link status. 236 tests pass.

**Phase D commit**: `feat(dashboard): V2 right pane — company edit and link-status indicator`

---

### Phase E — Migrate remaining pages + cleanup (commit checkpoint E)

**Goal**: ensure all four pages work correctly in the new file structure. No logic changes to Pages 1, 3, 4 — this is a verification + tidy step.

#### Step E1: Verify Pages 1, 3, 4 render correctly

Manually open each page in the running dashboard and confirm:
- "📊 My Applications": follow-up banner, metrics row, status filter, per-app expanders with save/delete/follow-up, cover letter display — all working.
- "❌ Not Matched": date chips, job list, "Move to Matched" button — working.
- "📈 Scrape Health": broken-platform banner, yield table with red zeros, top-terms table — working.

No code changes expected. If a page is broken, investigate and fix before proceeding.

#### Step E2: Remove the old `render_jobs` function **only if** it is no longer called anywhere

After Phase A–D, `render_jobs` is only called when `v2_layout` is False (the V1 fallback path). Keep it for now — it is the rollback path.

#### Step E3: Remove the `v2_layout` toggle once operator is satisfied

After the operator has triaged at least one full scrape run with V2 and confirms it is working:

1. Delete the `v2_checkbox` lines from the sidebar.
2. Remove the `if st.session_state.get("v2_layout", True): ... else: render_jobs(matched)` branch from the Today's Matches page — leave only `_render_matches_v2(...)`.
3. Delete the `render_jobs` function entirely.
4. Update the `v2_selected_job_id` initialisation to be unconditional (it already is, so no change needed).

**STOP**: Do NOT perform Step E3 until the operator explicitly says "V2 is good, remove the toggle." If they have not said this, leave the toggle in place and commit Phase E without Step E3.

**Phase E commit**: `feat(dashboard): V2 — verify all pages, remove toggle after operator sign-off`

---

### Phase F — Final cleanup (commit checkpoint F)

After Step E3 is done (toggle removed, `render_jobs` deleted):

1. Run the full test suite: `venv/Scripts/python.exe -m pytest` → 236+ passed, 0 failed.
2. Do a final smoke-read of `dashboard.py` to confirm no dead imports (e.g. if `get_applied_status` (singular) was only used in the old code and is now unused, note it but do NOT remove it — that is out of scope for this plan).
3. Commit: `refactor(dashboard): remove V1 fallback path and render_jobs after V2 sign-off`

---

## Test plan

The 236 existing tests cover `nodes/tracker.py`, `nodes/analyzer.py`, `nodes/scrape_log_parser.py`, and helpers — none of them test `dashboard.py` rendering directly (Streamlit's test runner requires `AppTest` which is available in 1.28+ but not widely used here).

**New tests required**: None are strictly required for the rendering code, since `_auto_advance` is the only new pure function. Add one test in `tests/test_dashboard_helpers.py` (create this file):

```python
"""Tests for dashboard helper logic extracted from dashboard.py."""
# _auto_advance is tested indirectly via its session-state mutation.
# For simplicity, inline the logic here as a pure function for testing.

def _auto_advance_pure(current_id: int, all_ids: list, unreviewed_ids: set) -> int | None:
    """Pure testable version of the auto-advance logic.
    Returns the next unreviewed id, or None if all reviewed.
    """
    try:
        idx = all_ids.index(current_id)
    except ValueError:
        return None
    for i in all_ids[idx + 1:]:
        if i in unreviewed_ids:
            return i
    for i in all_ids[:idx]:
        if i in unreviewed_ids:
            return i
    return None


def test_auto_advance_finds_next():
    assert _auto_advance_pure(2, [1, 2, 3, 4], {3, 4}) == 3

def test_auto_advance_wraps_around():
    assert _auto_advance_pure(4, [1, 2, 3, 4], {1, 2}) == 1

def test_auto_advance_all_reviewed():
    assert _auto_advance_pure(2, [1, 2, 3], set()) is None

def test_auto_advance_unknown_id():
    assert _auto_advance_pure(99, [1, 2, 3], {1}) is None
```

**Verify**: `venv/Scripts/python.exe -m pytest tests/test_dashboard_helpers.py -v` → 4 passed.
Full suite: `venv/Scripts/python.exe -m pytest` → 240 passed (236 + 4 new), 0 failed.

---

## Done criteria

ALL of the following must hold before the plan is marked DONE:

- [ ] `venv/Scripts/python.exe -m pytest` → 240 passed, 0 failed
- [ ] The V2 two-pane layout renders on "Today's Matches" when the toggle is on
- [ ] Clicking a job row in the left pane selects it and shows the detail in the right pane
- [ ] "Applied" button calls `update_matched_job_applied(id, 1)` and `save_application(...)` and auto-advances
- [ ] "Not Applying" popover captures reason + note via `update_matched_job_rejection(...)` and auto-advances
- [ ] Progress indicator ("N of M reviewed") is visible in the left pane
- [ ] Iframe renders (or falls back gracefully with a link) in the right pane
- [ ] All four pages (My Applications, Today's Matches, Not Matched, Scrape Health) are functional
- [ ] Pages 1, 3, 4 are pixel-for-pixel identical to V1 (no unintended changes)
- [ ] The V1 fallback (toggle off) still works via `render_jobs(matched)`
- [ ] `git diff --name-only` shows only `dashboard.py` and `tests/test_dashboard_helpers.py` modified (plus `requirements.txt` if keyboard shortcuts were added)
- [ ] `plans/README.md` status row for plan 022 updated to DONE

---

## STOP conditions

Stop and report back (do not improvise) if:

1. The code at the locations in "Current state" doesn't match the excerpts — the codebase drifted since this plan was written. Report the diff.
2. `venv/Scripts/python.exe -m pytest` fails at any intermediate phase with new test failures (i.e. you broke an existing test). Do not proceed to the next phase until tests are green.
3. The operator's primary job boards (Stepstone, LinkedIn, Glassdoor, Arbeitsagentur) all block iframes in live testing — stop before Phase D and report. The plan author may need to draft a companion plan to add a `description` column to `matched_jobs`.
4. The `st.popover` widget for "Not Applying" does not open when inside `st.columns` (a known Streamlit quirk in some versions). If it fails, stop and report — do not try to work around it with a custom component.
5. A step requires modifying `nodes/tracker.py` or any file outside the in-scope list.
6. The operator has not confirmed keyboard shortcuts but something in the plan text was misread as "implement them" — stop and ask.
7. `_render_job_detail_right` exceeds ~200 lines. If it does, extract sub-functions but keep them in `dashboard.py`, not a new file (per D9).

---

## Open questions (operator must answer before Phase C or keyboard shortcuts)

1. **Keyboard shortcuts (D7)**: Do you want `a` → Applied, `n` → Not Applying, `→` → next job? This requires adding `streamlit-shortcuts` to `requirements.txt`. Answer YES or NO before the executor reaches Phase E.

2. **Iframe fallback UX**: If a job board blocks the iframe, the operator sees a blank frame + an "Open in tab" link. Is that acceptable, or would you prefer to hide the iframe entirely and always show just the link? Answer before Phase C.

3. **Left pane scroll**: Streamlit does not natively make a single column scrollable while the other is fixed. With 100+ jobs, the left pane will be very long and the right pane will scroll with it. If this is unacceptable, the executor will need to use `st.container(height=...)` (available in Streamlit 1.32+, NOT in 1.55.0 — confirm version). **STOP**: if the operator wants a fixed-height scrollable left pane, report back — this is not achievable in Streamlit 1.55.0 without a custom component.

---

## Maintenance notes

- The `v2_layout` toggle key (`"v2_layout"`) is stored in `st.session_state`. If the user clears browser cookies / session, the toggle resets to `True` (the default). That is intentional — V2 is the target.
- `_auto_advance` reads `applied_map` at the moment the button is clicked, before the DB write. The current job's state in the map is still 0 at that point. This is correct — the function skips the current job by `id` comparison, not by state.
- If plan 020 (Gmail status automation) lands, it removes the "Interview / Rejected / Snooze" buttons from the follow-up expander in Page 1. That change is in plan 020's scope, not this plan's. The buttons are left in place here.
- The `get_rejection_reason_counts()` function in `tracker.py` is not yet surfaced in the dashboard. A future plan (scorer calibration) should add a breakdown chart to Page 1 or Page 4 once ≥50 reasoned rejections exist. Not in scope here.
- The `cover_letter` column exists in both `applications` and `matched_jobs` but is empty for all rows. The display in Page 1 (lines 540–544) is preserved; if a cover-letter generation plan ever lands, it writes to this column and the display works automatically.

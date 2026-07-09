"""Regression tests: PLATFORM_CONFIGS invariants that broke in the past."""
from nodes.scraper import PLATFORM_CONFIGS


def test_stepstone_card_selector_is_single_data_at():
    """Plan 018: the multi-selector union chain matched real cards PLUS
    filter-facet <article> elements Stepstone added around 2026-06-19,
    poisoning the extraction. A single-selector value is the correct shape
    for this platform; a comma reintroduces the union bug."""
    cs = PLATFORM_CONFIGS["Stepstone"]["card_selector"]
    assert cs == "article[data-at='job-item']", (
        f"Stepstone card_selector regressed to a chain — this reopens the "
        f"filter-facet pollution bug. Got: {cs!r}"
    )
    assert "," not in cs, "No comma allowed — union chains scoop facet articles"


def test_stepstone_inner_selectors_all_populated():
    """Guard against an accidental empty inner-selector list. Phase 1
    verified the historical inner selectors still extract cleanly from
    live Stepstone cards; keep them intact."""
    sel = PLATFORM_CONFIGS["Stepstone"]["selectors"]
    for field in ("title", "company", "location", "link"):
        assert sel.get(field), f"Stepstone selectors[{field!r}] is empty"
        assert len(sel[field]) >= 2, (
            f"Stepstone selectors[{field!r}] should have at least "
            f"primary + fallback"
        )

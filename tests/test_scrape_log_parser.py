import textwrap

from nodes.scrape_log_parser import (
    _parse_text,
    platform_history,
    broken_platforms,
    top_terms_aggregated,
)


SAMPLE_TWO_RUNS = textwrap.dedent("""\
    ╔══════════════════════════════════════════════════════════════════════╗
    ║  Scrape Summary — 2026-06-23 10:53:56                              ║
    ╠════════════════╦════════╦══════════╦════════╦═══════════╦═════════════╣
    ║ Platform       ║  Terms ║    Cards ║  Added ║     Exp ❌ ║      Depr ❌ ║
    ╠════════════════╬════════╬══════════╬════════╬═══════════╬═════════════╣
    ║ Arbeitsagentur ║     39 ║      367 ║    145 ║         0 ║          53 ║
    ║ Glassdoor      ║      3 ║       30 ║     17 ║         0 ║           8 ║
    ║ Indeed         ║      2 ║        0 ║      0 ║         0 ║           0 ║
    ║ LinkedIn       ║      8 ║      149 ║    107 ║         0 ║          38 ║
    ║ Stepstone      ║      2 ║        0 ║      0 ║         0 ║           0 ║
    ║ XING           ║      2 ║        0 ║      0 ║         0 ║           0 ║
    ╠════════════════╬════════╬══════════╬════════╬═══════════╬═════════════╣
    ║ TOTAL          ║     39 ║      546 ║    269 ║         0 ║          99 ║
    ╚══════════════════════════════════════════════════════════════════════╝
      Top terms by jobs added: Graduate Software Engineer (97), Vollzeit Softwareentwickler (36), Trainee Softwareentwicklung (19)

    ╔══════════════════════════════════════════════════════════════════════╗
    ║  Scrape Summary — 2026-06-29 17:31:38                              ║
    ╠════════════════╦════════╦══════════╦════════╦═══════════╦═════════════╣
    ║ Platform       ║  Terms ║    Cards ║  Added ║     Exp ❌ ║      Depr ❌ ║
    ╠════════════════╬════════╬══════════╬════════╬═══════════╬═════════════╣
    ║ Arbeitsagentur ║     39 ║      352 ║    137 ║         0 ║          55 ║
    ║ Glassdoor      ║      3 ║       30 ║     20 ║         0 ║           5 ║
    ║ Indeed         ║      2 ║        0 ║      0 ║         0 ║           0 ║
    ║ LinkedIn       ║      9 ║      568 ║    334 ║         0 ║          41 ║
    ║ Stepstone      ║      2 ║        0 ║      0 ║         0 ║           0 ║
    ║ XING           ║      2 ║        0 ║      0 ║         0 ║           0 ║
    ╠════════════════╬════════╬══════════╬════════╬═══════════╬═════════════╣
    ║ TOTAL          ║     39 ║      950 ║    491 ║         0 ║         101 ║
    ╚══════════════════════════════════════════════════════════════════════╝
      Top terms by jobs added: Graduate Software Engineer (253), Trainee IT (63), Vollzeit Softwareentwickler (35)
""")


def test_parse_two_runs_returns_two_dicts():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    assert len(runs) == 2
    assert runs[0]["timestamp"] == "2026-06-23 10:53:56"
    assert runs[1]["timestamp"] == "2026-06-29 17:31:38"


def test_parse_platforms_populated_and_totals_extracted():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    last = runs[-1]
    assert set(last["platforms"].keys()) == {"Arbeitsagentur", "Glassdoor", "Indeed", "LinkedIn", "Stepstone", "XING"}
    assert last["platforms"]["LinkedIn"]["added"] == 334
    assert last["platforms"]["Indeed"]["added"] == 0
    assert last["total"] == {"terms": 39, "cards": 950, "added": 491, "exp": 0, "depr": 101}


def test_parse_top_terms():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    assert runs[-1]["top_terms"][0] == ("Graduate Software Engineer", 253)
    assert len(runs[-1]["top_terms"]) == 3


def test_parse_empty_text_returns_empty_list():
    assert _parse_text("") == []
    assert _parse_text("noise\ndata\n") == []


def test_platform_history_slices_to_limit():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    hist = platform_history(runs, "LinkedIn", limit=1)
    assert len(hist) == 1
    assert hist[0]["added"] == 334


def test_platform_history_skips_runs_missing_platform():
    # Craft a run without Stepstone
    partial = SAMPLE_TWO_RUNS.replace("║ Stepstone      ║      2 ║        0 ║      0 ║         0 ║           0 ║\n", "", 2)
    runs = _parse_text(partial)
    assert platform_history(runs, "Stepstone", limit=5) == []


def test_broken_platforms_finds_three_consecutive_zero_added():
    # Repeat SAMPLE_TWO_RUNS to get a 3-run window with Indeed/Stepstone/XING at zero
    runs = _parse_text(SAMPLE_TWO_RUNS + SAMPLE_TWO_RUNS)
    broken = broken_platforms(runs, streak=3)
    for p in ("Indeed", "Stepstone", "XING"):
        assert p in broken
    for p in ("LinkedIn", "Arbeitsagentur", "Glassdoor"):
        assert p not in broken


def test_broken_platforms_empty_input():
    assert broken_platforms([], streak=3) == []


def test_broken_platforms_below_streak_length_no_alert():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    assert broken_platforms(runs, streak=3) == []  # only 2 runs in the log


def test_top_terms_aggregated_sums_across_runs():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    aggregated = top_terms_aggregated(runs, limit=5)
    top = dict(aggregated)
    assert top["Graduate Software Engineer"] == 97 + 253
    assert top["Vollzeit Softwareentwickler"] == 36 + 35


def test_top_terms_aggregated_respects_limit():
    runs = _parse_text(SAMPLE_TWO_RUNS)
    assert len(top_terms_aggregated(runs, limit=1)) == 1

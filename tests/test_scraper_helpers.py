import pytest

from nodes.scraper import _title_key, _url_key, deduplicate, extract_city


# ---------- extract_city ----------

def test_extract_city_postcode_plus_city():
    assert extract_city("44801 Bochum") == "Bochum"


def test_extract_city_comma_region():
    assert extract_city("Bochum, NRW") == "Bochum"


def test_extract_city_pipe_region():
    assert extract_city("Bochum | NRW") == "Bochum"


def test_extract_city_bullet_region():
    assert extract_city("Bochum • NRW") == "Bochum"


def test_extract_city_empty_returns_unknown():
    assert extract_city("") == "Unknown"


def test_extract_city_none_returns_unknown():
    assert extract_city(None) == "Unknown"


def test_extract_city_parens_stripped():
    # Postcode inside parens is stripped by _POSTCODE_RE first, then the "("
    # separator splits the string.
    assert extract_city("Bochum (44801)") == "Bochum"


def test_extract_city_district_gebiet_suffix_with_space_stripped():
    # NOTE: _DISTRICT_RE = r'\s+gebiet$' requires whitespace before "gebiet".
    # A compound like "Ruhrgebiet" is NOT stripped (no space). Only spaced
    # variants like "Ruhr Gebiet" (or here: "Bochum Gebiet, NRW" — the
    # separator splits, then the district regex trims "Gebiet").
    assert extract_city("Bochum Gebiet, NRW") == "Bochum"


def test_extract_city_compound_gebiet_not_stripped():
    # Documents current behavior — no whitespace, no strip.
    assert extract_city("Ruhrgebiet") == "Ruhrgebiet"


# ---------- _url_key ----------

def test_url_key_strips_query_string():
    assert _url_key("https://X.de/job/1?utm=ad") == "https://x.de/job/1"


def test_url_key_strips_trailing_slash():
    assert _url_key("https://X.de/job/1/") == "https://x.de/job/1"


def test_url_key_lowercases():
    assert _url_key("HTTPS://X.DE/JOB/1") == "https://x.de/job/1"


def test_url_key_empty_returns_empty():
    assert _url_key("") == ""


def test_url_key_none_returns_empty():
    assert _url_key(None) == ""


# ---------- _title_key ----------

def test_title_key_includes_company():
    job = {"title": "Junior Dev", "company": "Acme"}
    assert _title_key(job) == "junior dev_acme"


def test_title_key_strips_gender_parens():
    job = {"title": "Junior Dev (m/w/d)", "company": "Acme"}
    assert _title_key(job) == "junior dev_acme"


@pytest.mark.parametrize("company", ["Unknown", "unknown", "", "n/a"])
def test_title_key_drops_unknown_company(company):
    job = {"title": "Junior Dev", "company": company}
    assert _title_key(job) == "junior dev"


# ---------- deduplicate ----------

def test_deduplicate_same_url_produces_single_entry():
    # NOTE: When two jobs share the same normalized URL, deduplicate keeps
    # ONE entry and does NOT append the duplicate URL to its `urls` list —
    # the append at scraper.py:172 guards against same-ukey duplicates.
    jobs = [
        {"title": "Junior Dev", "company": "Acme",
         "url": "https://a.com/1", "platform": "linkedin"},
        {"title": "Junior Dev", "company": "Acme",
         "url": "https://a.com/1?utm=x", "platform": "xing"},
    ]
    out = deduplicate(jobs)
    assert len(out) == 1
    assert len(out[0]["urls"]) == 1
    assert out[0]["urls"][0]["platform"] == "linkedin"


def test_deduplicate_same_title_company_different_urls_merges():
    jobs = [
        {"title": "Junior Dev", "company": "Acme",
         "url": "https://a.com/1", "platform": "linkedin"},
        {"title": "Junior Dev", "company": "Acme",
         "url": "https://b.com/2", "platform": "xing"},
    ]
    out = deduplicate(jobs)
    assert len(out) == 1
    platforms = sorted(e["platform"] for e in out[0]["urls"])
    assert platforms == ["linkedin", "xing"]


def test_deduplicate_merges_across_gender_suffix_variants():
    jobs = [
        {"title": "Junior Dev (m/w/d)", "company": "Acme",
         "url": "https://a.com/1", "platform": "linkedin"},
        {"title": "Junior Dev (w/m/d)", "company": "Acme",
         "url": "https://b.com/2", "platform": "xing"},
    ]
    out = deduplicate(jobs)
    assert len(out) == 1
    assert len(out[0]["urls"]) == 2


def test_deduplicate_upgrades_unknown_location():
    # NOTE: Company-upgrade branch at scraper.py:189-191 is effectively
    # unreachable — Unknown-company and known-company jobs land in
    # different tkey buckets (see _title_key). Location upgrade at :192-194
    # DOES trigger because location is not part of the key.
    jobs = [
        {"title": "Junior Dev", "company": "Acme", "location": "Unknown",
         "url": "https://a.com/1", "platform": "linkedin"},
        {"title": "Junior Dev", "company": "Acme", "location": "Bochum",
         "url": "https://b.com/2", "platform": "xing"},
    ]
    out = deduplicate(jobs)
    assert len(out) == 1
    assert out[0]["location"] == "Bochum"


def test_deduplicate_distinct_jobs_kept_separate():
    jobs = [
        {"title": "Junior Dev", "company": "Acme",
         "url": "https://a.com/1", "platform": "linkedin"},
        {"title": "Senior QA", "company": "Beta",
         "url": "https://b.com/2", "platform": "xing"},
    ]
    out = deduplicate(jobs)
    assert len(out) == 2

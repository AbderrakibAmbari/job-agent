import pytest

from nodes.tracker import _norm_title, _norm_company, _title_company_key


@pytest.mark.parametrize("raw, expected", [
    ("Junior Dev (m/w/d)", "junior dev"),
    ("Junior Dev (w/m/d)", "junior dev"),
    ("Junior Dev (m/f/d)", "junior dev"),
    ("Junior Dev (f/m/d)", "junior dev"),
    ("Junior Dev (m/w/x)", "junior dev"),
    ("Junior Dev (w/m/x)", "junior dev"),
    ("Junior Dev (f/m/x)", "junior dev"),
    ("Junior Dev (all genders)", "junior dev"),
    ("Junior Dev (M/W/D)", "junior dev"),
    ("Junior Dev (All Genders)", "junior dev"),
    ("Backend Engineer(m/w/d)", "backend engineer"),
])
def test_norm_title_strips_gender_suffix_case_insensitive(raw, expected):
    assert _norm_title(raw) == expected


@pytest.mark.parametrize("title, company, expected", [
    pytest.param(
        "Linux/Unix Systems Engineer (f/m/d)", "Hyundai AutoEver Europe GmbH",
        "linux/unix systems engineer|hyundai autoever europe",
        id="strips_f_m_d_variant",
    ),
    pytest.param(
        "Data Analyst (f/m/x)", "Acme",
        "data analyst|acme",
        id="strips_f_m_x_variant",
    ),
])
def test_title_company_key_strips_female_first_gender_variants(title, company, expected):
    assert _title_company_key(title, company) == expected


def test_norm_title_lowercases_and_strips_edges():
    assert _norm_title("  BACKEND Engineer  ") == "backend engineer"


def test_norm_title_preserves_internal_whitespace():
    assert _norm_title("Junior   Backend Dev") == "junior   backend dev"


def test_norm_title_none_returns_empty():
    assert _norm_title(None) == ""


def test_norm_title_empty_returns_empty():
    assert _norm_title("") == ""


@pytest.mark.parametrize("raw, expected", [
    ("Acme GmbH", "acme"),
    ("Acme AG", "acme"),
    ("Acme SE", "acme"),
    ("Acme Ltd", "acme"),
    ("Acme Ltd.", "acme"),
    ("Acme LLC", "acme"),
    ("Acme Inc", "acme"),
    ("Acme Inc.", "acme"),
    ("Acme KG", "acme"),
    ("Acme e.V.", "acme"),
    ("Acme gGmbH", "acme"),
    ("Acme plc", "acme"),
    ("Acme GmbH & Co. KG", "acme"),
    ("Acme GmbH & Co KG", "acme"),
    ("ACME GMBH", "acme"),
])
def test_norm_company_strips_legal_suffix(raw, expected):
    assert _norm_company(raw) == expected


def test_norm_company_collapses_internal_whitespace():
    assert _norm_company("Acme   Corp  GmbH") == "acme corp"


def test_norm_company_none_returns_empty():
    assert _norm_company(None) == ""


def test_norm_company_empty_returns_empty():
    assert _norm_company("") == ""


def test_title_company_key_includes_known_company():
    assert _title_company_key("Junior Dev", "Acme GmbH") == "junior dev|acme"


@pytest.mark.parametrize("company", ["Unknown", "unknown", "UNKNOWN", "", "n/a", "N/A"])
def test_title_company_key_drops_unknown_company(company):
    assert _title_company_key("Junior Dev", company) == "junior dev"


def test_title_company_key_merges_across_gender_and_suffix_variants():
    a = _title_company_key("Junior Dev (m/w/d)", "Acme GmbH")
    b = _title_company_key("Junior Dev (w/m/d)", "Acme AG")
    c = _title_company_key("Junior Dev (all genders)", "Acme GmbH & Co. KG")
    assert a == b == c == "junior dev|acme"

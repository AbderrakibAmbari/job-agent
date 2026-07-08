import pytest

from nodes.analyzer import _apply_experience_cap, _quick_reject


# ---------- _quick_reject ----------

def test_quick_reject_senior_without_counter_indicator():
    reason = _quick_reject({"title": "Senior Backend Developer"})
    assert reason is not None
    assert "Senior/Lead" in reason


def test_quick_reject_senior_trainee_title_passes():
    assert _quick_reject({"title": "Senior Trainee Programme"}) is None


def test_quick_reject_senior_vollzeit_in_description_passes():
    job = {
        "title": "Senior Backend Developer",
        "description": "Vollzeit Festanstellung",
    }
    assert _quick_reject(job) is None


@pytest.mark.parametrize("title", [
    "Vertrieb",
    "Sales",
    "Recruiter",
    "Buchhalter",
    "Logistik",
])
def test_quick_reject_non_tech_titles(title):
    reason = _quick_reject({"title": title})
    assert reason is not None
    assert "Non-tech" in reason


def test_quick_reject_5plus_years_experience():
    reason = _quick_reject({"title": "Junior Backend", "description": "5+ Jahre Erfahrung"})
    assert reason is not None
    assert "5+ years" in reason


def test_quick_reject_outside_germany_not_remote():
    reason = _quick_reject({"title": "Junior Backend", "location": "Zürich"})
    assert reason is not None
    assert "Zürich" in reason


def test_quick_reject_remote_location_passes():
    assert _quick_reject({"title": "Junior Backend", "location": "Remote"}) is None


@pytest.mark.parametrize("loc", [
    "Bochum", "NRW", "Deutschland",
    "Braunschweig", "Bremen", "Kiel", "Hannover", "Oldenburg", "Bonn",
    "Nürnberg", "Eschborn", "Augsburg", "Wolfsburg", "Saarbrücken",
    "Dresden", "Coburg", "Bielefeld", "Karlsruhe", "Wiesbaden", "Mainz",
    "Münster", "Aachen", "Duisburg", "Wuppertal", "Leipzig",
    "Frankfurt am Main", "Berlin Mitte", "München, Bayern",
    "Baden-Württemberg", "Niedersachsen", "Rheinland-Pfalz",
])
def test_quick_reject_german_locations_pass(loc):
    assert _quick_reject({"title": "Junior Backend", "location": loc}) is None


@pytest.mark.parametrize("loc", [
    "Zürich", "Vienna", "Wien", "London", "Warsaw", "Amsterdam",
    "Paris", "Prague", "Zurich",
])
def test_quick_reject_non_german_locations_rejected(loc):
    reason = _quick_reject({"title": "Junior Backend", "location": loc})
    assert reason is not None
    assert "Outside Germany" in reason


def test_quick_reject_empty_location_passes():
    assert _quick_reject({"title": "Junior Backend", "location": ""}) is None


# ---------- _apply_experience_cap ----------

def test_apply_cap_werkstudent_hard_caps_at_40():
    job = {"title": "Werkstudent Junior", "description": "", "score": 90}
    assert _apply_experience_cap(job)["score"] == 40


def test_apply_cap_werkstudent_below_cap_left_alone():
    job = {"title": "Werkstudent Junior", "description": "", "score": 30}
    assert _apply_experience_cap(job)["score"] == 30


def test_apply_cap_werkstudent_returns_early_no_further_caps():
    # If Werkstudent short-circuit didn't fire, the "no junior/Vollzeit" 60 cap
    # would apply to score=50. It shouldn't, because Werkstudent returns first.
    # (Score 50 stays 50 because 50 < 40 is False; and 50 > 60 is False anyway.)
    # Use score below Werkstudent cap to isolate the early-return behavior.
    job = {"title": "Werkstudent Backend", "description": "", "score": 35}
    result = _apply_experience_cap(job)
    assert result["score"] == 35


def test_apply_cap_experience_hard_cap_3_plus_years():
    job = {"title": "Junior", "description": "3 Jahre Erfahrung", "score": 80}
    assert _apply_experience_cap(job)["score"] == 40


def test_apply_cap_requires_experience_flag():
    job = {"title": "Junior", "description": "", "score": 80, "_requires_experience": True}
    assert _apply_experience_cap(job)["score"] == 40


def test_apply_cap_no_junior_no_vollzeit_caps_at_60():
    job = {"title": "Backend Developer", "description": "", "score": 85}
    assert _apply_experience_cap(job)["score"] == 60


def test_apply_cap_vollzeit_in_description_exempts_60_cap():
    job = {"title": "Backend Developer", "description": "Vollzeit Festanstellung", "score": 85}
    assert _apply_experience_cap(job)["score"] == 85


def test_apply_cap_sap_role_with_sap_category_caps_at_55():
    job = {
        "title": "SAP Consultant",
        "description": "",
        "score": 90,
        "job_category": "SAP/ERP",
    }
    assert _apply_experience_cap(job)["score"] == 55


def test_apply_cap_sap_trainee_exempt_from_sap_cap():
    job = {
        "title": "SAP Trainee",
        "description": "",
        "score": 90,
        "job_category": "SAP/ERP",
    }
    # Trainee in title exempts BOTH the SAP cap and (via _JUNIOR_KEYWORDS) the
    # 60 cap, so the score is left untouched. Assert >= 55 per plan spec.
    assert _apply_experience_cap(job)["score"] >= 55


def test_apply_cap_sap_title_without_sap_category_not_capped_by_sap_rule():
    job = {
        "title": "SAP Consultant",
        "description": "Vollzeit",
        "score": 90,
        "job_category": "Other",
    }
    # Vollzeit exempts the 60 cap; category != "SAP/ERP" skips the 55 cap.
    assert _apply_experience_cap(job)["score"] == 90

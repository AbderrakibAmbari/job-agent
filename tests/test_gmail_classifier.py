"""Rule-based Gmail classifier tests (plan 020 phase 1).

Real German + English samples, anonymised. If a variant here regresses,
the classifier lost a signal — either fix the rule that shifted or add
the new variant to the rules deliberately.
"""
import pytest

from nodes.gmail_classifier import classify_message


def _msg(subject: str = "", body: str = "") -> dict:
    return {"subject": subject, "body": body}


# ---------- Rejection (DE) ----------

REJECTION_DE = [
    ("Absage zu Ihrer Bewerbung", ""),
    ("Ihre Bewerbung bei uns", "Leider können wir Ihnen keine Zusage geben."),
    ("Update Ihrer Bewerbung", "Wir bedauern, Ihnen mitteilen zu müssen, dass wir uns anders entschieden haben."),
    ("Bewerbung Software Engineer", "Vielen Dank. Leider können wir Sie nicht weiter berücksichtigen."),
    ("Rückmeldung", "Sie haben es leider nicht in die engere Auswahl geschafft."),
    ("Ihre Bewerbung", "Wir haben uns für einen anderen Kandidaten entschieden."),
]


@pytest.mark.parametrize("subject,body", REJECTION_DE)
def test_classify_rejection_de(subject, body):
    assert classify_message(_msg(subject, body)) == "Rejected"


# ---------- Rejection (EN) ----------

REJECTION_EN = [
    ("Application update", "We regret to inform you that we won't be moving forward."),
    ("Backend Engineer application", "Unfortunately, we are not able to proceed with your application."),
    ("Your application", "We have decided to move forward with another candidate."),
    ("Thanks for your interest", "The position has been filled."),
    ("Update", "Not moving forward with your candidacy at this time."),
]


@pytest.mark.parametrize("subject,body", REJECTION_EN)
def test_classify_rejection_en(subject, body):
    assert classify_message(_msg(subject, body)) == "Rejected"


# ---------- Interview (DE) ----------

INTERVIEW_DE = [
    ("Einladung zum Vorstellungsgespräch", ""),
    ("Ihre Bewerbung", "Wir möchten Sie gerne persönlich kennenlernen."),
    ("Terminvorschlag Interview", "Wann passt es Ihnen für ein erstes Gespräch?"),
    ("Nächste Schritte", "Als nächster Schritt möchten wir Sie zu einem Videocall einladen."),
]


@pytest.mark.parametrize("subject,body", INTERVIEW_DE)
def test_classify_interview_de(subject, body):
    assert classify_message(_msg(subject, body)) == "Interview"


# ---------- Interview (EN) ----------

INTERVIEW_EN = [
    ("Interview invitation", ""),
    ("Next steps", "We'd like to invite you for a first conversation."),
    ("Your application", "The next step is a video call with the hiring team."),
    ("Availability", "Can we schedule a call this week?"),
]


@pytest.mark.parametrize("subject,body", INTERVIEW_EN)
def test_classify_interview_en(subject, body):
    assert classify_message(_msg(subject, body)) == "Interview"


# ---------- Offer ----------

OFFER = [
    ("Ihr Vertragsangebot", ""),
    ("Employment offer", "We're pleased to offer you the position."),
    ("Angebot", "Anbei senden wir Ihnen den Arbeitsvertrag."),
    ("Formal offer", "Please find attached the formal offer of employment."),
]


@pytest.mark.parametrize("subject,body", OFFER)
def test_classify_offer(subject, body):
    assert classify_message(_msg(subject, body)) == "Offer"


# ---------- Autoack (Waiting) ----------

AUTOACK = [
    ("Bewerbungseingang", "Vielen Dank für Ihre Bewerbung."),
    ("Eingangsbestätigung", "Diese E-Mail wurde automatisch generiert."),
    ("Application received", "Do not reply to this email."),
    ("Thank you for applying", "This is an automated confirmation."),
]


@pytest.mark.parametrize("subject,body", AUTOACK)
def test_classify_autoack_returns_waiting(subject, body):
    assert classify_message(_msg(subject, body)) == "Waiting"


# ---------- No signal ----------

NO_SIGNAL = [
    ("Newsletter der Woche", "Diese Woche neue Jobs im Bereich Backend."),
    ("Vernetzen wir uns?", "Ich bin Recruiter und suche einen Backend Engineer."),
    ("", ""),
]


@pytest.mark.parametrize("subject,body", NO_SIGNAL)
def test_classify_no_signal(subject, body):
    assert classify_message(_msg(subject, body)) is None


# ---------- Precedence: rejection wins over interview when both hint appear ----------

def test_rejection_wins_over_interview_when_both_present():
    """A rejection body that also mentions 'interview' historically should classify as Rejected."""
    msg = _msg(
        subject="Update your application",
        body="Thank you for the interview last week. Unfortunately, we are not moving forward.",
    )
    assert classify_message(msg) == "Rejected"


def test_offer_beats_interview_when_offer_language_present():
    msg = _msg(
        subject="Nächste Schritte",
        body="Wir freuen uns, Ihnen ein Vertragsangebot zu unterbreiten.",
    )
    # rejection tag isn't there, interview isn't there, offer is → Offer
    assert classify_message(msg) == "Offer"

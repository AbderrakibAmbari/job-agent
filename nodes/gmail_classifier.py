"""Classify a Gmail message into an application status.

Plan 020 phase 1: regex-first, LLM-only-for-residue. The rules should
handle >95% of real mails. Anything they miss is optionally routed to
Haiku 4.5 with a strict output budget.

Returns one of: "Rejected", "Interview", "Offer", "Waiting", or None.
None = no signal, don't touch the row (recruiter cold outreach, an
unrelated newsletter matched by mistake).
"""
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Match order: rejection > interview > offer > autoack > None.
# Rejection first because "Einladung zur Absage" is not a real invite —
# rejection wording is dominant when present.

_REJECTION_PATTERNS = [
    # DE
    r"\babsage\b",
    r"\bleider\b.{0,80}\b(nicht|kein|keine)\b",
    r"\bbedauern\b",
    r"\bnicht (weiter |mehr )?berücksichtigen\b",
    r"\bnicht in die (engere|nächste)\b",
    r"\bandere.{0,40}entschieden\b",
    r"\buns gegen (Sie|dich)\b",
    r"\bhaben uns entschieden.{0,60}(anderen|weiterzugehen)\b",
    # EN
    r"\bwe regret\b",
    r"\bunfortunately\b.{0,80}\b(not|unable)\b",
    r"\bnot (moving forward|selected|proceeding)\b",
    r"\bdecided to move (forward|on) with (another|other)\b",
    r"\bposition has been filled\b",
    r"\bother candidates\b.{0,40}\b(match|fit|closer)\b",
]

_INTERVIEW_PATTERNS = [
    # DE
    r"\beinladung zum (interview|gespräch|kennenlernen|vorstellungsgespräch)\b",
    r"\b(?:möchten wir|wir möchten) (?:Sie|dich) gerne\b.{0,80}\b(einladen|kennenlernen|einem gespräch)\b",
    r"\bterminvorschlag\b",
    r"\b(video[-\s]?call|zoom[-\s]?einladung|teams[-\s]?meeting)\b",
    r"\berstes gespräch\b",
    r"\bnächster schritt\b.{0,60}\b(gespräch|interview|call)\b",
    # EN
    r"\bwe(?:'d| would) like to invite you\b",
    r"\binterview (invitation|scheduled|slot)\b",
    r"\bnext step is (?:a )?(?:video|phone|zoom|teams) call\b",
    r"\bschedule (?:a )?(?:call|chat|interview)\b",
    r"\bmove(?: you)? forward to (?:a |the )?(?:first |next )?(?:interview|conversation)\b",
]

_OFFER_PATTERNS = [
    # DE
    r"\bvertragsangebot\b",
    r"\bwir freuen uns\b.{0,80}\beinstellung\b",
    r"\barbeitsvertrag\b",
    r"\bstellenzusage\b",
    # EN
    r"\bwe(?:'re| are) pleased to offer\b",
    r"\boffer of employment\b",
    r"\bemployment agreement\b",
    r"\bformal offer\b",
]

# Autoacks tend to be short and dominated by "we received your application" —
# they shouldn't flip the row to anything terminal.
_AUTOACK_SUBJECT_PATTERNS = [
    r"\bbewerbungseingang\b",
    r"\bihre bewerbung\b.{0,40}\b(eingegangen|erhalten)\b",
    r"\bapplication received\b",
    r"\bthank you for applying\b",
    r"\bapplication confirmation\b",
    r"\beingangsbestätigung\b",
]

_AUTOACK_BODY_HINTS = [
    r"\bautomatisch generiert\b",
    r"\bdo not reply\b",
    r"\bnoreply\b",
    r"\bthis is an automated\b",
    r"\bdiese e-mail wurde automatisch\b",
]


def _compile(patterns):
    return [re.compile(p, re.IGNORECASE | re.DOTALL) for p in patterns]


_REJ_RE = _compile(_REJECTION_PATTERNS)
_INT_RE = _compile(_INTERVIEW_PATTERNS)
_OFF_RE = _compile(_OFFER_PATTERNS)
_AUTO_SUBJ_RE = _compile(_AUTOACK_SUBJECT_PATTERNS)
_AUTO_BODY_RE = _compile(_AUTOACK_BODY_HINTS)


def _any(regexes, text: str) -> bool:
    return any(r.search(text) for r in regexes)


def classify_message(msg: dict) -> Optional[str]:
    """Rule-based classification.

    Returns "Rejected"/"Interview"/"Offer"/"Waiting"/None. Autoacks are
    "Waiting" — they confirm the pipeline is alive but don't change state.
    """
    subject = (msg.get("subject") or "").lower()
    body = (msg.get("body") or "").lower()
    # First 1000 chars only — pattern signals are always up top, footers
    # from ATS platforms often contain unrelated boilerplate that trips patterns.
    body_head = body[:2000]

    if _any(_REJ_RE, body_head) or _any(_REJ_RE, subject):
        return "Rejected"
    if _any(_INT_RE, body_head) or _any(_INT_RE, subject):
        return "Interview"
    if _any(_OFF_RE, body_head) or _any(_OFF_RE, subject):
        return "Offer"
    if _any(_AUTO_SUBJ_RE, subject) or _any(_AUTO_BODY_RE, body_head):
        return "Waiting"
    return None


def classify_with_llm(msg: dict) -> str:
    """LLM fallback for residue. Returns Rejected/Interview/Offer/Waiting.

    Called only from the backfill script's residue loop and bounded by a
    per-run call budget there.
    """
    from langchain_anthropic import ChatAnthropic
    from dotenv import load_dotenv

    load_dotenv()
    llm = ChatAnthropic(
        model=os.getenv("GMAIL_CLASSIFIER_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=8,
    )

    subject = msg.get("subject", "")
    body = (msg.get("body") or "")[:1500]
    prompt = (
        "You classify job application emails into exactly one label: "
        "Rejected, Interview, Offer, or Waiting.\n\n"
        "Rules:\n"
        "- Rejected: the company said no or moved on with others.\n"
        "- Interview: they want to schedule a call/interview.\n"
        "- Offer: they extended an employment offer.\n"
        "- Waiting: autoack, informational, or no clear signal.\n\n"
        f"Subject: {subject}\n"
        f"Body: {body}\n\n"
        "Answer with one word: Rejected, Interview, Offer, or Waiting."
    )
    try:
        response = llm.invoke(prompt)
        text = (response.content or "").strip()
        for label in ("Rejected", "Interview", "Offer", "Waiting"):
            if label.lower() in text.lower():
                return label
    except Exception as e:
        logger.warning("LLM classification failed: %s", e)
    return "Waiting"

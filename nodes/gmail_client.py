"""Gmail API client — OAuth2 installed-app flow, read-only scope.

Plan 020 phase 1: backfill classifier reads Gmail. No writes here — the
Gmail account is source of truth for status; this module just fetches
messages and hands them off.

First-run flow: the operator downloads a Desktop-app OAuth client from
Google Cloud Console → `data/gmail_credentials.json`. `get_service()`
opens a browser once for consent, stores a refresh token at
`data/gmail_token.json`. Subsequent runs reuse the token.
"""
import base64
import logging
import os
import time
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_CREDENTIALS_PATH = "data/gmail_credentials.json"
_TOKEN_PATH = "data/gmail_token.json"


def get_service():
    """Return an authorized Gmail API service. Prompts for consent on first run."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds: Optional[Credentials] = None
    if os.path.exists(_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(_TOKEN_PATH, _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(_CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Missing {_CREDENTIALS_PATH}. Download a Desktop OAuth client "
                    "from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(_CREDENTIALS_PATH, _SCOPES)
            creds = flow.run_local_server(port=0)
        with open(_TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def list_messages(service, query: str, page_size: int = 100) -> Iterable[dict]:
    """Yield message stubs {"id": ..., "threadId": ...} matching `query`.

    `query` uses Gmail search syntax, e.g. `after:2026/01/10 -in:sent -label:draft`.
    Paginates until exhausted. Rate-limit-aware.
    """
    request = service.users().messages().list(
        userId="me", q=query, maxResults=page_size
    )
    while request is not None:
        response = _with_backoff(lambda r=request: r.execute())
        for msg in response.get("messages", []) or []:
            yield msg
        request = service.users().messages().list_next(request, response)


def get_message(service, msg_id: str) -> dict:
    """Fetch a full message, return normalized dict.

    Keys: id, thread_id, from, subject, date, snippet, body.
    Body is the plain-text part (or HTML stripped to plain if no plain part).
    """
    raw = _with_backoff(
        lambda: service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
    )
    payload = raw.get("payload", {}) or {}
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    body = _extract_body(payload)
    return {
        "id": raw.get("id"),
        "thread_id": raw.get("threadId"),
        "from": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "snippet": raw.get("snippet", "") or "",
        "body": body,
    }


def _extract_body(payload: dict) -> str:
    """Walk MIME parts, return the first text/plain body decoded to str.

    Falls back to text/html with tags stripped if no text/plain exists.
    """
    mime = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")
    if mime == "text/plain" and data:
        return _decode(data)
    if mime.startswith("multipart/"):
        parts = payload.get("parts", []) or []
        for part in parts:
            if part.get("mimeType") == "text/plain":
                d = part.get("body", {}).get("data")
                if d:
                    return _decode(d)
        for part in parts:
            nested = _extract_body(part)
            if nested:
                return nested
        for part in parts:
            if part.get("mimeType") == "text/html":
                d = part.get("body", {}).get("data")
                if d:
                    return _strip_html(_decode(d))
    if mime == "text/html" and data:
        return _strip_html(_decode(data))
    return ""


def _decode(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    """Cheap HTML→text. Avoids adding a dep just for this."""
    import re as _re
    text = _re.sub(r"<script.*?</script>", " ", html, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r"<style.*?</style>", " ", text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r"<[^>]+>", " ", text)
    text = _re.sub(r"\s+", " ", text)
    return text.strip()


def _with_backoff(fn, max_attempts: int = 4):
    """Retry a callable on transient Google API errors with exponential backoff."""
    from googleapiclient.errors import HttpError

    delay = 2.0
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except HttpError as e:
            status = getattr(e, "status_code", None) or (
                e.resp.status if getattr(e, "resp", None) else None
            )
            if status in (429, 500, 502, 503, 504):
                last_exc = e
                logger.warning("Gmail API %s, retrying in %.1fs", status, delay)
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
                continue
            raise
        except Exception as e:  # network hiccups
            last_exc = e
            logger.warning("Gmail API error %s, retrying in %.1fs", e, delay)
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
    assert last_exc is not None
    raise last_exc

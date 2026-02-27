"""
gmail.py — Google OAuth2 flow and Gmail polling for Lucilease.

OAuth notes:
- Credentials (client_id / client_secret) come from environment variables.
- User token is stored in /data/token.json (Docker volume, gitignored).
- First-time auth: user visits /auth/gmail → Google → /auth/callback.
- For the unverified-app warning during testing: add the realtor's Google
  account as a Test User in Google Cloud Console → OAuth consent screen.
"""

import os
import re
import base64
import email.mime.text
import pathlib
import sqlite3
from typing import Optional

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from leads import parse_email_to_lead, make_fingerprint
from db import get_conn

# ── Config ────────────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]

TOKEN_FILE = pathlib.Path("/data/token.json")
REDIRECT_URI = "http://localhost:8080/auth/callback"


def strip_html(html: str) -> str:
    """Convert HTML (from contenteditable) to clean plain text for email sending."""
    if not html:
        return ""
    # Block-level tags → newlines
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|li|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Strip all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    text = (text
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&nbsp;", " ")
            .replace("&#39;", "'")
            .replace("&quot;", '"'))
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _client_config() -> dict:
    return {
        "web": {
            "client_id":     os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
            "token_uri":     "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }


# ── OAuth helpers ─────────────────────────────────────────────────────────────

def get_auth_url() -> str:
    """Return the Google OAuth2 authorization URL."""
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return url


def exchange_code(code: str) -> None:
    """Exchange auth code for tokens and save to TOKEN_FILE."""
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    flow.fetch_token(code=code)
    _save_token(flow.credentials)
    print("[gmail] OAuth complete. Token saved.")


def get_credentials() -> Optional[Credentials]:
    """Load and refresh stored credentials, or return None if not authed."""
    if not TOKEN_FILE.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_token(creds)
        return creds if creds.valid else None
    except Exception as e:
        print(f"[gmail] Credential error: {e}")
        return None


def is_authenticated() -> bool:
    return get_credentials() is not None


def _save_token(creds: Credentials) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json())


# ── Gmail polling ─────────────────────────────────────────────────────────────

def poll_inbox(label_ids: list[str] = None) -> int:
    """
    Fetch unread inbox messages, parse into leads, and store new ones.
    Returns the count of new leads found.
    """
    creds = get_credentials()
    if not creds:
        print("[gmail] Not authenticated — skipping poll.")
        return 0

    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    conn    = get_conn()
    new_count = 0

    try:
        # Scan last 7 days of inbox (read + unread) — dedup handles repeats
        query  = "in:inbox newer_than:7d"
        if label_ids:
            query += " " + " ".join(f"label:{l}" for l in label_ids)
        result = service.users().messages().list(
            userId="me", q=query, maxResults=100
        ).execute()

        messages = result.get("messages", [])
        print(f"[gmail] Found {len(messages)} unread message(s).")

        for msg_ref in messages:
            msg_id = msg_ref["id"]

            # Skip if we've already processed this message
            existing = conn.execute(
                "SELECT id FROM leads WHERE gmail_msg_id=?", (msg_id,)
            ).fetchone()
            if existing:
                continue

            # Fetch full message
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()

            headers_raw = msg["payload"].get("headers", [])
            headers     = {h["name"]: h["value"] for h in headers_raw}
            body        = _extract_body(msg["payload"])

            lead = parse_email_to_lead(headers, body, msg_id=msg_id)

            # Dedup by fingerprint
            dup = conn.execute(
                "SELECT id FROM leads WHERE fingerprint=?", (lead.fingerprint,)
            ).fetchone()
            if dup:
                print(f"[gmail] Duplicate lead skipped: {lead.from_email}")
                continue

            # Insert
            conn.execute("""
                INSERT INTO leads
                    (fingerprint, source, from_email, name, phone, subject,
                     body_excerpt, budget_monthly_usd, status, first_seen_at, gmail_msg_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                lead.fingerprint, lead.source, lead.from_email, lead.name,
                lead.phone, lead.subject, lead.body_excerpt,
                lead.budget_monthly_usd, "new", lead.first_seen_at,
                lead.gmail_msg_id,
            ))
            conn.commit()
            new_count += 1
            print(f"[gmail] New lead: {lead.from_email} ({lead.fingerprint[:10]}...)")

    except Exception as e:
        print(f"[gmail] Poll error: {e}")
    finally:
        conn.close()

    return new_count


def _extract_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    mime = payload.get("mimeType", "")

    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    if mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            text = _extract_body(part)
            if text:
                return text

    return ""


def send_gmail_message(creds, to: str, subject: str, body: str,
                       thread_id=None) -> str:
    """Send an email immediately. Returns sent message id."""
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    msg = email.mime.text.MIMEText(strip_html(body))
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body_dict: dict = {"raw": raw}
    if thread_id:
        body_dict["threadId"] = thread_id
    result = service.users().messages().send(userId="me", body=body_dict).execute()
    return result["id"]


def update_gmail_draft(creds, draft_id: str, to: str, subject: str, body: str) -> str:
    """Update an existing Gmail draft. Returns draft id."""
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    msg = email.mime.text.MIMEText(strip_html(body))
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = service.users().drafts().update(
        userId="me", id=draft_id,
        body={"message": {"raw": raw}}
    ).execute()
    return result["id"]


def send_gmail_draft(creds, draft_id: str) -> str:
    """Send an existing Gmail draft by id. Returns sent message id."""
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    result = service.users().drafts().send(
        userId="me", body={"id": draft_id}
    ).execute()
    return result["id"]


def create_gmail_draft_public(creds, to: str, subject: str, body: str,
                               thread_id=None) -> str:
    """Public wrapper to create a Gmail draft. Returns draft id."""
    return _create_gmail_draft_impl(creds, to, subject, body, thread_id)


def _create_gmail_draft_impl(creds, to: str, subject: str, body: str,
                              thread_id=None) -> str:
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    msg = email.mime.text.MIMEText(strip_html(body))
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft_body: dict = {"message": {"raw": raw}}
    if thread_id:
        draft_body["message"]["threadId"] = thread_id
    draft = service.users().drafts().create(userId="me", body=draft_body).execute()
    return draft["id"]

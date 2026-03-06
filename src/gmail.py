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
    "https://www.googleapis.com/auth/gmail.modify",    # read + label/archive ops
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events", # calendar read/write
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
        if not creds.valid:
            return None
        return creds
    except Exception as e:
        print(f"[gmail] Credential error: {e}")
        return None


def get_granted_scopes() -> list[str]:
    """Return the scopes actually granted in the stored token (not just requested)."""
    if not TOKEN_FILE.exists():
        return []
    try:
        import json
        data = json.loads(TOKEN_FILE.read_text())
        raw = data.get("scopes") or data.get("scope") or ""
        if isinstance(raw, list):
            return raw
        return raw.split() if raw else []
    except Exception:
        return []


def check_scopes_ok() -> dict:
    """
    Verify the stored token has all required scopes.
    Returns {"ok": bool, "missing": [...], "granted": [...]}.
    """
    granted = set(get_granted_scopes())
    required = set(SCOPES)
    missing  = required - granted
    return {"ok": len(missing) == 0, "missing": list(missing), "granted": list(granted)}


def is_authenticated() -> bool:
    return get_credentials() is not None


def _save_token(creds: Credentials) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json())


# ── Gmail polling ─────────────────────────────────────────────────────────────

# ── Housing relevance filter ──────────────────────────────────────────────────
# ── Inbox filter ─────────────────────────────────────────────────────────────
#
# PHILOSOPHY: err heavily on the side of letting emails through.
# The filter's ONLY job is blocking obvious automated/spam/newsletter mail
# from completely unknown senders. Everything else passes.
#
# Set LUCILEASE_NO_FILTER=1 in .env to disable entirely.

# Positive signals — any match means it's almost certainly relevant
HOUSING_KEYWORDS = [
    "rent", "rental", "apartment", "lease", "listing", "property", "properties",
    "house", "home", "bedroom", "studio", "unit", "available", "availability",
    "showing", "tour", "move in", "move-in", "vacancy", "tenant", "landlord",
    "square feet", "sq ft", "sqft", "deposit", "pet friendly", "furnished",
    "real estate", "realty", "realtor", "for rent", "for sale", "buy", "buying",
    "mortgage", "down payment", "open house", "floor plan", "sq. ft",
    "price", "monthly", "budget", "looking for", "interested in",
]

# Hard spam/automation signals — if any match on an unknown sender, skip it
SPAM_SIGNALS = [
    "unsubscribe", "opt out", "opt-out", "no-reply", "noreply",
    "do not reply", "donotreply", "mailing list", "newsletter",
    "subscription", "automated message", "this is an automated",
    "out of office", "auto-reply", "autoreply", "auto reply",
    "delivery status", "mailer-daemon", "postmaster",
    "you are receiving this", "to stop receiving",
    "©", "click here to unsubscribe", "manage your preferences",
    "privacy policy", "terms of service",
]

def _extract_email_addr(raw: str) -> str:
    """Extract bare email address from 'Name <email@x.com>' or 'email@x.com'."""
    raw = (raw or "").strip()
    if "<" in raw and ">" in raw:
        return raw.split("<")[-1].replace(">", "").strip().lower()
    return raw.lower()


def _is_spam_or_automated(subject: str, body: str, headers: dict) -> bool:
    """Return True if this looks like automated/newsletter/spam mail."""
    text = ((subject or "") + " " + (body or "")[:500]).lower()
    # Check content signals
    if any(sig in text for sig in SPAM_SIGNALS):
        return True
    # Check common spam headers
    precedence = headers.get("Precedence", "").lower()
    if precedence in ("bulk", "list", "junk"):
        return True
    list_id = headers.get("List-ID") or headers.get("List-Id")
    if list_id:
        return True
    auto_submitted = headers.get("Auto-Submitted", "").lower()
    if auto_submitted and auto_submitted != "no":
        return True
    return False


def should_admit_email(subject: str, body: str, headers: dict, conn) -> tuple[bool, str]:
    """
    Decide if an incoming email should be admitted to the Lucilease inbox.

    Returns (admit: bool, reason: str)

    Priority order:
    1. LUCILEASE_NO_FILTER=1 → always admit
    2. Automated/spam signals → always block
    3. Reply chain (Re:) → always admit
    4. Sender is a known lead or client → always admit
    5. Lucilease has previously sent email to this address → always admit
    6. Thread ID matches a tracked lead/appointment → always admit
    7. Housing keyword present → admit
    8. Everything else → block (unknown cold email with no housing signal)
    """
    _no_filter = os.environ.get("LUCILEASE_NO_FILTER", "").strip() == "1"
    if not _no_filter:
        try:
            row = conn.execute("SELECT value FROM config WHERE key='no_filter'").fetchone()
            if row and row["value"] == "1":
                _no_filter = True
        except Exception:
            pass
    if _no_filter:
        return True, "filter_disabled"

    # Block automated/spam mail first regardless of anything else
    if _is_spam_or_automated(subject, body, headers):
        return False, "spam_or_automated"

    # Reply chain — always let through, Lucilease may have sent the original
    subj_clean = (subject or "").strip().lower()
    if subj_clean.startswith("re:") or subj_clean.startswith("fwd:"):
        return True, "reply_chain"

    from_addr = _extract_email_addr(headers.get("From", ""))

    # Known lead
    if conn.execute("SELECT 1 FROM leads WHERE lower(from_email)=? LIMIT 1", (from_addr,)).fetchone():
        return True, "known_lead"

    # Known client
    if conn.execute("SELECT 1 FROM clients WHERE lower(email)=? LIMIT 1", (from_addr,)).fetchone():
        return True, "known_client"

    # Lucilease has previously sent an email to this address (drafts table, status=sent)
    if conn.execute("SELECT 1 FROM drafts WHERE lower(to_email)=? AND status='sent' LIMIT 1", (from_addr,)).fetchone():
        return True, "previously_contacted"

    # Thread ID known
    thread_id = headers.get("_thread_id")  # injected by caller if available
    if thread_id:
        if conn.execute("SELECT 1 FROM leads WHERE gmail_thread_id=? LIMIT 1", (thread_id,)).fetchone():
            return True, "known_thread"
        if conn.execute("SELECT 1 FROM appointments WHERE thread_id=? LIMIT 1", (thread_id,)).fetchone():
            return True, "known_appointment_thread"

    # Housing keyword present — cold inquiry from unknown sender
    text = ((subject or "") + " " + (body or "")).lower()
    if any(kw in text for kw in HOUSING_KEYWORDS):
        return True, "housing_keyword"

    return False, "no_signal"


# Legacy shim — kept for any internal callers that haven't been updated
def _is_housing_relevant(subject: str, body: str) -> bool:
    text = ((subject or "") + " " + (body or "")).lower()
    if os.environ.get("LUCILEASE_NO_FILTER", "").strip() == "1":
        return True
    return any(kw in text for kw in HOUSING_KEYWORDS)


CONFIRMATION_KEYWORDS = [
    # Direct confirmations
    "confirmed", "it's confirmed", "all confirmed", "appointment confirmed",
    "that's confirmed", "yes, confirmed",
    # See you
    "see you", "see you then", "see you at", "see you there", "see you soon",
    "i'll see you", "we'll see you", "we will see you",
    # Works / agreement
    "that works", "this works", "works for me", "works for us", "works great",
    "that works for me", "that works for us", "this works for me",
    "that time works", "this time works", "the time works",
    "works perfectly", "works well", "perfect timing",
    # Affirmative short replies
    "yes!", "yes,", "yes that", "yes this", "yes it", "yes i", "yes we",
    "sounds good", "sounds great", "sounds perfect", "sounds like a plan",
    "perfect", "perfect!", "great!", "awesome!", "wonderful!",
    "absolutely", "definitely", "for sure", "of course",
    # Looking forward
    "looking forward to meeting", "looking forward to seeing", "looking forward to it",
    "looking forward to the", "can't wait", "excited to see",
    # Scheduling language
    "scheduled for", "we're all set", "all set", "we are all set",
    "i'll be there", "we'll be there", "i will be there", "we will be there",
    "meet you at", "meet you there", "meet you then",
    "set for", "booked for", "we're meeting", "it's a date",
    # Day/time confirmations
    "saturday works", "sunday works", "monday works", "tuesday works",
    "wednesday works", "thursday works", "friday works",
    "saturday is good", "sunday is good", "monday is good",
    "that day works", "that day is good", "that day is great",
    "morning works", "afternoon works", "evening works",
]

INQUIRY_KEYWORDS = [
    "what time", "what times", "when are you available", "when can we",
    "any availability", "any available", "available times", "available slots",
    "open slots", "open times", "what days", "what day works",
    "when works for you", "when is good for you", "schedule a showing",
    "schedule a tour", "schedule a visit", "book a showing", "book a tour",
    "can we see it", "can i see it", "interested in viewing",
    "would love to see", "love to tour", "arrange a showing",
    "set up a viewing", "set up a showing", "when can i come",
    "when can we come", "when can we visit", "when can we see",
]

def is_confirmation_candidate(subject: str, body: str) -> bool:
    """Quick pre-filter: does this email look like a meeting confirmation?"""
    text = ((subject or "") + " " + (body or "")).lower()
    return any(kw in text for kw in CONFIRMATION_KEYWORDS)

def is_availability_inquiry(subject: str, body: str) -> bool:
    """Quick pre-filter: is the client asking about available times/slots?"""
    text = ((subject or "") + " " + (body or "")).lower()
    return any(kw in text for kw in INQUIRY_KEYWORDS)


def scan_sent_for_confirmations() -> list[dict]:
    """
    Scan sent mail from the last 7 days for confirmation candidates.
    Returns list of {msg_id, thread_id, headers, body} for qualifying messages.
    """
    creds = get_credentials()
    if not creds:
        return []

    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    conn    = get_conn()
    results = []

    try:
        query  = "in:sent newer_than:7d"
        result = service.users().messages().list(
            userId="me", q=query, maxResults=100
        ).execute()

        for msg_ref in result.get("messages", []):
            msg_id = msg_ref["id"]
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
            thread_id   = msg.get("threadId")
            headers_raw = msg["payload"].get("headers", [])
            headers     = {h["name"]: h["value"] for h in headers_raw}
            body        = _extract_body(msg["payload"])
            subject     = headers.get("Subject", "")

            if not _is_housing_relevant(subject, body):
                continue
            if not is_confirmation_candidate(subject, body):
                continue

            # Skip threads already tracked as appointments
            existing = conn.execute(
                "SELECT id FROM appointments WHERE thread_id=? AND status != 'deleted'",
                (thread_id,)
            ).fetchone()
            if existing:
                continue

            results.append({
                "msg_id":    msg_id,
                "thread_id": thread_id,
                "headers":   headers,
                "body":      body,
                "subject":   subject,
            })
    except Exception as e:
        print(f"[gmail] scan_sent error: {e}")
    finally:
        conn.close()

    return results


def poll_inbox(label_ids: list[str] = None) -> int:
    """
    Fetch inbox messages from the last 7 days, filter for housing relevance,
    parse into leads, and store new ones. Returns count of new leads found.
    """
    creds = get_credentials()
    if not creds:
        print("[gmail] Not authenticated — skipping poll.")
        return 0

    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    conn    = get_conn()
    new_count = 0

    # Get the agent's own email to filter self-sent messages from inbox
    try:
        agent_email = service.users().getProfile(userId="me").execute().get("emailAddress", "").lower()
    except Exception:
        agent_email = ""

    try:
        # Use last-poll timestamp to avoid re-scanning old mail on every refresh.
        # Falls back to 2d on first run; 7d only on explicit full-rescan.
        last_poll_row = conn.execute(
            "SELECT value FROM config WHERE key='last_poll_at'"
        ).fetchone()
        if last_poll_row and last_poll_row["value"]:
            import email.utils as _eu
            # Gmail `after:` uses Unix timestamp
            import datetime as _dt
            lp = _dt.datetime.fromisoformat(last_poll_row["value"].replace("Z",""))
            after_ts = int(lp.timestamp())
            query = f"in:inbox after:{after_ts}"
        else:
            query = "in:inbox newer_than:2d"
        if label_ids:
            query += " " + " ".join(f"label:{l}" for l in label_ids)

        result = service.users().messages().list(
            userId="me", q=query, maxResults=100
        ).execute()

        messages = result.get("messages", [])
        print(f"[gmail] Found {len(messages)} message(s) in inbox scan (query: {query!r}).")

        # Pre-fetch all known msg_ids in one DB query for fast dedup
        known_ids = set(
            r[0] for r in conn.execute("SELECT gmail_msg_id FROM leads WHERE gmail_msg_id IS NOT NULL").fetchall()
        )

        new_msg_ids = [m["id"] for m in messages if m["id"] not in known_ids]
        print(f"[gmail] {len(new_msg_ids)} new message(s) after dedup.")

        for msg_id in new_msg_ids:
            # Fetch full message only for genuinely new ones
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()

            # Always recheck DB (race condition safety)
            if conn.execute("SELECT 1 FROM leads WHERE gmail_msg_id=?", (msg_id,)).fetchone():
                continue

            headers_raw = msg["payload"].get("headers", [])
            headers     = {h["name"]: h["value"] for h in headers_raw}
            body        = _extract_body(msg["payload"])

            subject   = headers.get("Subject", "")
            thread_id = msg.get("threadId")
            # Inject thread_id into headers dict for should_admit_email lookup
            headers["_thread_id"] = thread_id

            # Skip emails sent FROM the agent's own account (e.g. outgoing replies in inbox)
            from_raw  = headers.get("From", "")
            from_addr = _extract_email_addr(from_raw)
            if agent_email and from_addr == agent_email:
                continue

            admit, reason = should_admit_email(subject, body, headers, conn)
            if not admit:
                print(f"[gmail] Filtered ({reason}): {subject!r}")
                continue
            print(f"[gmail] Admitted ({reason}): {subject!r}")
            lead = parse_email_to_lead(headers, body, msg_id=msg_id)

            # Fingerprint dedup ONLY for cold first-contact emails (housing_keyword reason).
            # Replies and messages from known contacts must always be inserted —
            # the same person can send many messages in a thread. gmail_msg_id (checked
            # above) is the true unique key; fingerprint only guards against duplicate
            # cold leads from the same person.
            if reason == "housing_keyword":
                dup = conn.execute(
                    "SELECT id FROM leads WHERE fingerprint=?", (lead.fingerprint,)
                ).fetchone()
                if dup:
                    print(f"[gmail] Duplicate cold lead skipped: {lead.from_email}")
                    continue

            # Use a per-message fingerprint for non-cold emails so the UNIQUE constraint
            # on fingerprint doesn't block the insert
            fp = lead.fingerprint if reason == "housing_keyword" else f"msg_{msg_id}"

            # Insert — store full body + thread id
            conn.execute("""
                INSERT INTO leads
                    (fingerprint, source, from_email, name, phone, subject,
                     body_excerpt, body_full, budget_monthly_usd, status,
                     first_seen_at, gmail_msg_id, gmail_thread_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                fp, lead.source, lead.from_email, lead.name,
                lead.phone, lead.subject, lead.body_excerpt, lead.body_full,
                lead.budget_monthly_usd, "new", lead.first_seen_at,
                lead.gmail_msg_id, thread_id,
            ))
            conn.commit()
            new_count += 1
            print(f"[gmail] New lead: {lead.from_email} — {subject!r}")

    except Exception as e:
        print(f"[gmail] Poll error: {e}")
    finally:
        conn.close()

    return new_count


def _extract_body(payload: dict) -> str:
    """
    Recursively extract readable body text from a Gmail message payload.
    Prefers text/plain; falls back to stripped text/html.
    Handles nested multipart structures (multipart/alternative, /related, /mixed).
    """
    mime = payload.get("mimeType", "")

    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    if mime == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            html = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            return strip_html(html)

    if mime.startswith("multipart/"):
        parts = payload.get("parts", [])
        # For multipart/alternative prefer plain text (usually first)
        plain_result = ""
        html_result = ""
        for part in parts:
            part_mime = part.get("mimeType", "")
            if part_mime == "text/plain":
                plain_result = _extract_body(part)
            elif part_mime == "text/html" and not plain_result:
                html_result = _extract_body(part)
            elif part_mime.startswith("multipart/"):
                nested = _extract_body(part)
                if nested:
                    plain_result = plain_result or nested
        return plain_result or html_result

    return ""


def get_thread_messages(creds, thread_id: str) -> list[dict]:
    """
    Fetch all messages in a Gmail thread.
    Returns list of dicts: {from, date, subject, body} sorted oldest-first.
    """
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    thread = service.users().threads().get(
        userId="me", id=thread_id, format="full"
    ).execute()

    result = []
    for msg in thread.get("messages", []):
        headers_raw = msg["payload"].get("headers", [])
        headers = {h["name"]: h["value"] for h in headers_raw}
        body = _extract_body(msg["payload"])
        result.append({
            "msg_id":  msg["id"],
            "from":    headers.get("From", ""),
            "to":      headers.get("To", ""),
            "date":    headers.get("Date", ""),
            "subject": headers.get("Subject", ""),
            "body":    body,
        })
    return result  # Gmail returns oldest-first by default


def archive_gmail_message(creds, msg_id: str) -> bool:
    """
    Archive a Gmail message by removing the INBOX label.
    Returns True on success, False if msg_id is None or call fails.
    Requires gmail.modify scope.
    """
    if not msg_id:
        print("[gmail] archive_gmail_message: no msg_id, skipping.")
        return False
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    result = service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["INBOX"]},
    ).execute()
    print(f"[gmail] Archived {msg_id} — labels now: {result.get('labelIds', [])}")
    return True


def get_rfc_message_id(creds, gmail_thread_id: str) -> Optional[str]:
    """
    Fetch the RFC Message-ID header from the LAST message in a thread.
    Used to set In-Reply-To + References so replies thread correctly everywhere.
    """
    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        thread  = service.users().threads().get(
            userId="me", id=gmail_thread_id, format="metadata",
            metadataHeaders=["Message-ID"]
        ).execute()
        messages = thread.get("messages", [])
        if not messages:
            return None
        last_msg = messages[-1]
        for h in last_msg.get("payload", {}).get("headers", []):
            if h["name"].lower() == "message-id":
                return h["value"]
    except Exception as e:
        print(f"[gmail] get_rfc_message_id error: {e}")
    return None


def send_gmail_message(creds, to: str, subject: str, body: str,
                       thread_id=None, in_reply_to: Optional[str] = None) -> str:
    """
    Send an email immediately. Returns sent message id.
    Pass thread_id to keep it in the same Gmail thread.
    Pass in_reply_to (RFC Message-ID) to set proper reply headers.
    If thread_id is given but in_reply_to is not, we auto-fetch the RFC id.
    """
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    # Resolve sender address from Gmail profile so From header is correct
    try:
        profile = service.users().getProfile(userId="me").execute()
        sender  = profile.get("emailAddress", "me")
    except Exception:
        sender = "me"

    # Auto-fetch RFC Message-ID for proper threading if not supplied
    if thread_id and not in_reply_to:
        in_reply_to = get_rfc_message_id(creds, thread_id)

    msg = email.mime.text.MIMEText(strip_html(body), "plain", "utf-8")
    msg["to"]      = to
    msg["from"]    = sender
    msg["subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"]  = in_reply_to

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body_dict: dict = {"raw": raw}
    if thread_id:
        body_dict["threadId"] = thread_id

    print(f"[gmail] Sending email → {to} | subject: {subject!r} | thread: {thread_id or 'none'} | from: {sender}")
    result = service.users().messages().send(userId="me", body=body_dict).execute()
    print(f"[gmail] ✅ Sent OK — message id: {result.get('id')}")
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

    # Fetch RFC Message-ID for proper reply threading
    in_reply_to = None
    if thread_id:
        in_reply_to = get_rfc_message_id(creds, thread_id)

    try:
        profile = service.users().getProfile(userId="me").execute()
        sender  = profile.get("emailAddress", "me")
    except Exception:
        sender = "me"

    msg = email.mime.text.MIMEText(strip_html(body), "plain", "utf-8")
    msg["to"]      = to
    msg["from"]    = sender
    msg["subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"]  = in_reply_to

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft_body: dict = {"message": {"raw": raw}}
    if thread_id:
        draft_body["message"]["threadId"] = thread_id
    draft = service.users().drafts().create(userId="me", body=draft_body).execute()
    return draft["id"]

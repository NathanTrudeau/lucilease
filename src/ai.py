"""
ai.py — Claude Sonnet draft reply engine for Lucilease.

Given a lead and the agent's profile + property list, generates a
personalized, professional reply and saves it as a Gmail draft.
"""

import os
from typing import Optional
import anthropic

from db import get_conn
import gmail as gm
from googleapiclient.discovery import build
import base64
import email.mime.text


# ── Client ────────────────────────────────────────────────────────────────────

def _claude() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# ── Agent profile ─────────────────────────────────────────────────────────────

def get_agent_profile() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM config").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def save_agent_profile(profile: dict):
    from datetime import datetime
    now = datetime.utcnow().isoformat() + "Z"
    conn = get_conn()
    for key, value in profile.items():
        conn.execute("""
            INSERT INTO config (key, value, updated_at) VALUES (?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """, (key, value, now))
    conn.commit()
    conn.close()


# ── Draft generation ──────────────────────────────────────────────────────────

def draft_reply(lead_id: int) -> dict:
    """
    Generate a personalized reply for a lead using Claude Sonnet.
    Returns {"subject": str, "body": str, "gmail_draft_id": str|None}
    """
    conn = get_conn()
    lead = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not lead:
        conn.close()
        raise ValueError(f"Lead {lead_id} not found")

    lead = dict(lead)

    # Fetch active properties for context
    properties = [
        dict(r) for r in conn.execute(
            "SELECT * FROM properties WHERE status='active' ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
    ]
    conn.close()

    profile = get_agent_profile()
    agent_name    = profile.get("agent_name", "Your Agent")
    agent_company = profile.get("agent_company", "")
    agent_tone    = profile.get("agent_tone", "professional and warm")

    # Build properties context
    props_text = ""
    if properties:
        props_text = "\n\nAvailable properties you represent:\n"
        for p in properties:
            price = (f"${p['price_monthly']:,}/mo" if p.get("price_monthly")
                     else f"${p['price_sale']:,}" if p.get("price_sale") else "price TBD")
            beds  = f"{p['bedrooms']}bd/{p['bathrooms']}ba" if p.get("bedrooms") else ""
            props_text += f"- {p['address']} | {p['type']} | {beds} | {price}\n"
            if p.get("notes"):
                props_text += f"  Notes: {p['notes']}\n"

    # Budget context
    budget_ctx = ""
    if lead.get("budget_monthly_usd"):
        budget_ctx = f"Their stated budget is ${lead['budget_monthly_usd']:,}/month."

    sig_enabled = profile.get("agent_signature_enabled", "false") == "true"
    signature   = profile.get("agent_signature", "").strip() if sig_enabled else ""

    prompt = f"""You are {agent_name}, a real estate agent{f' at {agent_company}' if agent_company else ''}.
Tone: {agent_tone}.

A potential client emailed you. Write a SHORT, professional reply — no fluff, no filler.

Client inquiry:
- Name: {lead.get('name') or 'the sender'}
- Subject: {lead.get('subject') or 'N/A'}
- Message: {lead.get('body_excerpt') or 'N/A'}
- {budget_ctx}
{props_text}

Rules:
- Maximum 3 short paragraphs. Aim for under 120 words total.
- First paragraph: warm one-line greeting + acknowledge their specific need.
- Second paragraph: if a matching property exists, mention it in one sentence. Otherwise skip.
- Third paragraph: one clear call to action (schedule a showing or quick call).
- Do NOT use "I hope this email finds you well" or any filler openers.
- Do NOT include a subject line or signature — those are added separately.
- Plain text only, no markdown.
"""

    response = _claude().messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    body    = response.content[0].text.strip()
    if signature:
        body = body + "\n\n" + signature
    subject = f"Re: {lead.get('subject') or 'Your Inquiry'}"

    # Save draft to DB
    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    conn = get_conn()
    cursor = conn.execute("""
        INSERT INTO drafts (lead_id, subject, body, created_at)
        VALUES (?,?,?,?)
    """, (lead_id, subject, body, now))
    draft_db_id = cursor.lastrowid
    conn.commit()

    # Push to Gmail drafts if authenticated
    gmail_draft_id = None
    creds = gm.get_credentials()
    if creds and lead.get("gmail_msg_id"):
        try:
            gmail_draft_id = _create_gmail_draft(
                creds=creds,
                to=lead["from_email"],
                subject=subject,
                body=body,
                thread_id=_get_thread_id(creds, lead["gmail_msg_id"]),
            )
            conn.execute(
                "UPDATE drafts SET gmail_draft_id=? WHERE id=?",
                (gmail_draft_id, draft_db_id),
            )
            conn.commit()
        except Exception as e:
            print(f"[ai] Gmail draft creation failed: {e}")

    conn.close()

    return {
        "subject":        subject,
        "body":           body,
        "gmail_draft_id": gmail_draft_id,
        "draft_db_id":    draft_db_id,
    }


# ── Gmail draft helpers ───────────────────────────────────────────────────────

def _get_thread_id(creds, msg_id: str) -> Optional[str]:
    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="metadata", metadataHeaders=["threadId"]
        ).execute()
        return msg.get("threadId")
    except Exception:
        return None


def _create_gmail_draft(creds, to: str, subject: str, body: str,
                        thread_id: Optional[str] = None) -> str:
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    from gmail import strip_html
    msg = email.mime.text.MIMEText(strip_html(body))
    msg["to"]      = to
    msg["subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft_body: dict = {"message": {"raw": raw}}
    if thread_id:
        draft_body["message"]["threadId"] = thread_id

    draft = service.users().drafts().create(userId="me", body=draft_body).execute()
    return draft["id"]

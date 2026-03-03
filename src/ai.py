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

def assess_thread_tone(thread_text: str) -> dict:
    """
    Quick Claude check: is this thread angry, confusing, or off-topic?
    Returns {"flag": None|"angry"|"confusing"|"off_topic", "reason": str}
    """
    import json as _j
    prompt = f"""Briefly assess this email or thread. Respond with ONLY a JSON object:
{{
  "flag": null or "angry" or "confusing" or "off_topic",
  "reason": "one sentence explanation, or null"
}}

Set flag to:
- "angry": customer is clearly upset, frustrated, or using hostile language
- "confusing": thread is so unclear/jumbled that a meaningful reply is impossible  
- "off_topic": clearly unrelated to real estate / scheduling (e.g. wrong recipient)
- null: normal, safe to draft a reply

Email/thread:
{thread_text[:1500]}"""

    try:
        response = _claude().messages.create(
            model="claude-sonnet-4-5",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        return _j.loads(text)
    except Exception as e:
        print(f"[ai] assess_thread_tone error: {e}")
        return {"flag": None, "reason": None}


def draft_reply(lead_id: int) -> dict:
    """
    Generate a personalized reply for a lead using Claude Sonnet.
    Returns {"subject": str, "body": str, "gmail_draft_id": str|None}
    If the thread is flagged as angry/confusing/off-topic, returns
    {"flag": "angry"|"confusing"|"off_topic", "reason": str, "needs_review": True}
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

    # Fetch open house slots for active properties
    open_house_slots = {}
    for p in properties:
        slots = conn.execute(
            "SELECT * FROM open_house_slots WHERE property_id=? ORDER BY day_of_week, start_time",
            (p["id"],)
        ).fetchall()
        if slots:
            open_house_slots[p["id"]] = [dict(s) for s in slots]

    # Fetch agent availability windows + timezone from config
    cfg = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM config").fetchall()}
    timezone = cfg.get("timezone", "America/Los_Angeles")
    avail_raw = cfg.get("availability_windows")
    conn.close()

    profile = get_agent_profile()
    agent_name    = profile.get("agent_name", "Your Agent")
    agent_company = profile.get("agent_company", "")
    agent_tone    = profile.get("agent_tone", "professional and warm")

    # Build properties context (with open house windows per property)
    DAY_SHORT = {"monday":"Mon","tuesday":"Tue","wednesday":"Wed","thursday":"Thu",
                 "friday":"Fri","saturday":"Sat","sunday":"Sun"}
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
            slots = open_house_slots.get(p["id"], [])
            if slots:
                slot_strs = [
                    f"{DAY_SHORT.get(s['day_of_week'], s['day_of_week'])} {s['start_time']}–{s['end_time']}"
                    + (f" ({s['label']})" if s.get('label') else "")
                    for s in slots
                ]
                props_text += f"  Open house times: {', '.join(slot_strs)}\n"

    # Build agent availability context
    avail_text = ""
    if avail_raw:
        try:
            import json
            windows = json.loads(avail_raw)
            enabled = [w for w in windows if w.get("enabled")]
            if enabled:
                avail_lines = [
                    f"{DAY_SHORT.get(w['day'], w['day'])} {w['start']}–{w['end']}"
                    for w in enabled
                ]
                avail_text = f"\n\nYour general availability for appointments ({timezone}): {', '.join(avail_lines)}."
        except Exception:
            pass

    # Budget context
    budget_ctx = ""
    if lead.get("budget_monthly_usd"):
        budget_ctx = f"Their stated budget is ${lead['budget_monthly_usd']:,}/month."

    sig_enabled = profile.get("agent_signature_enabled", "false") == "true"
    signature   = profile.get("agent_signature", "").strip() if sig_enabled else ""

    # Quick tone/sanity check before drafting
    thread_text = (lead.get("body_full") or lead.get("body_excerpt") or "").strip()
    if thread_text:
        tone = assess_thread_tone(thread_text)
        if tone.get("flag"):
            return {
                "ok": False,
                "flag": tone["flag"],
                "reason": tone.get("reason") or "Thread flagged by AI — review before replying.",
                "needs_review": True,
                "lead_id": lead_id,
                "subject": f"Re: {lead.get('subject') or 'Your Inquiry'}",
            }

    prompt = f"""You are {agent_name}, a real estate agent{f' at {agent_company}' if agent_company else ''}.
Tone: {agent_tone}.

A potential client emailed you. Write a SHORT, professional reply — no fluff, no filler.

Client inquiry:
- Name: {lead.get('name') or 'the sender'}
- Subject: {lead.get('subject') or 'N/A'}
- Message: {lead.get('body_excerpt') or 'N/A'}
- {budget_ctx}
{props_text}{avail_text}

Rules:
- Maximum 3 short paragraphs. Aim for under 120 words total.
- First paragraph: warm one-line greeting + acknowledge their specific need.
- Second paragraph: if a matching property exists, mention it briefly. Otherwise skip.
- Third paragraph: one clear call to action — if suggesting a showing or meeting, propose a SPECIFIC time that fits within your open house windows or general availability above. Do not suggest vague times like "sometime this week".
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


# ── Confirmation detection ────────────────────────────────────────────────────

def detect_confirmation(thread_messages: list[dict]) -> dict | None:
    """
    Ask Claude if this thread contains a confirmed appointment.
    Returns extracted data dict or None if no confirmation found.
    """
    if not thread_messages:
        return None

    thread_text = "\n\n---\n\n".join([
        f"From: {m['from']}\nDate: {m['date']}\n\n{m['body']}"
        for m in thread_messages[-6:]  # last 6 messages max
    ])

    prompt = f"""Analyze this email thread. Determine if a specific meeting, showing, appointment, or phone call has been CONFIRMED by both parties — meaning both sides have agreed on a specific time.

Email thread:
{thread_text[:3000]}

Respond with ONLY a JSON object, no other text:
{{
  "confirmed": true or false,
  "meeting_type": "showing" | "call" | "open_house" | "coffee" | "other" | null,
  "proposed_datetime": "YYYY-MM-DDTHH:MM:SS" or null,
  "proposed_date_text": "human readable date/time string",
  "proposed_address": "address or location string" or null,
  "client_name": "client first/full name" or null,
  "client_email": "client email address" or null,
  "partner_name": "partner or spouse name if explicitly mentioned" or null,
  "context_snippet": "one sentence summary of what was confirmed",
  "confidence": "high" | "medium" | "low"
}}

Only set confirmed=true if there is clear mutual agreement on a specific time.
Vague interest, questions about availability, or one-sided proposals do NOT count."""

    import json
    response = _claude().messages.create(
        model="claude-sonnet-4-5",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if "```" in text:
        text = text.split("```")[1].replace("json", "").strip()

    try:
        data = json.loads(text)
    except Exception as e:
        print(f"[ai] detect_confirmation JSON parse error: {e} — raw: {text[:200]}")
        return None

    if not data.get("confirmed") or data.get("confidence") == "low":
        return None

    return data


def detect_availability_inquiry(thread_messages: list[dict]) -> dict | None:
    """
    Ask Claude if this thread contains a client asking about available times/slots.
    Returns extracted data dict or None if not an availability inquiry.
    """
    if not thread_messages:
        return None

    thread_text = "\n\n---\n\n".join([
        f"From: {m['from']}\nDate: {m['date']}\n\n{m['body']}"
        for m in thread_messages[-4:]
    ])

    prompt = f"""Analyze this email thread. Determine if the CLIENT is asking about available times, scheduling a showing, or requesting to set up a visit/tour for a property.

Email thread:
{thread_text[:2500]}

Respond with ONLY a JSON object, no other text:
{{
  "is_inquiry": true or false,
  "meeting_type": "showing" | "call" | "open_house" | "other" | null,
  "proposed_address": "property address if mentioned" or null,
  "client_name": "client first/full name" or null,
  "client_email": "client email address" or null,
  "partner_name": "partner or spouse if mentioned" or null,
  "context_snippet": "one sentence: what they are asking about",
  "confidence": "high" | "medium" | "low"
}}

Set is_inquiry=true only if the client is actively requesting to schedule or asking about times.
General interest without a scheduling request does NOT count."""

    import json
    response = _claude().messages.create(
        model="claude-sonnet-4-5",
        max_tokens=350,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1].replace("json", "").strip()

    try:
        data = json.loads(text)
    except Exception as e:
        print(f"[ai] detect_availability_inquiry JSON parse error: {e} — raw: {text[:200]}")
        return None

    if not data.get("is_inquiry") or data.get("confidence") == "low":
        return None

    return data


def draft_availability_options(appointment_id: int) -> dict:
    """
    Claude drafts a reply offering 2-3 specific available time slots to a client
    who asked about scheduling. Frames it as proactive offer, not an apology.
    Saves as local draft + pushes to Gmail.
    """
    import json as _json
    import datetime as _dt

    conn = get_conn()
    appt = conn.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
    cfg  = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM config").fetchall()}
    conn.close()

    if not appt:
        raise ValueError(f"Appointment {appointment_id} not found")
    appt = dict(appt)

    profile    = get_agent_profile()
    agent_name = profile.get("agent_name", "Your Agent")
    timezone   = cfg.get("timezone", "America/Los_Angeles")
    avail_raw  = cfg.get("availability_windows")

    avail_text = "weekdays 9am–6pm"
    if avail_raw:
        try:
            windows = _json.loads(avail_raw)
            enabled = [w for w in windows if w.get("enabled")]
            DAY_SHORT = {"monday":"Mon","tuesday":"Tue","wednesday":"Wed",
                         "thursday":"Thu","friday":"Fri","saturday":"Sat","sunday":"Sun"}
            if enabled:
                avail_text = ", ".join(
                    f"{DAY_SHORT.get(w['day'], w['day'])} {w['start']}–{w['end']}"
                    for w in enabled
                )
        except Exception:
            pass

    sig_enabled = profile.get("agent_signature_enabled", "false") == "true"
    signature   = profile.get("agent_signature", "").strip() if sig_enabled else ""
    today_str   = _dt.datetime.now().strftime("%A, %B %d, %Y")
    client_name = appt.get("client_name") or "there"
    address     = appt.get("proposed_address") or "the property"

    prompt = f"""You are {agent_name}, a real estate agent. A client has asked about your availability for a showing or visit.

Property: {address}
Your availability ({timezone}): {avail_text}
Today: {today_str}

Write a SHORT, warm reply offering 2-3 SPECIFIC available time slots in the next 1–2 weeks.

Rules:
- Start directly with the offer — no "great question" filler
- Offer 2–3 specific options like "Tuesday March 10th at 10am, Thursday March 12th at 2pm, or Saturday March 14th at 11am"
- Ask them to confirm whichever works best
- Under 80 words total
- No subject line, no signature, plain text only"""

    response = _claude().messages.create(
        model="claude-sonnet-4-5",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    body = response.content[0].text.strip()
    if signature:
        body = body + "\n\n" + signature

    subject = f"Re: {(appt.get('context_snippet') or 'Scheduling')[:60]}"
    now     = _dt.datetime.utcnow().isoformat() + "Z"

    conn = get_conn()
    cursor = conn.execute("""
        INSERT INTO drafts (lead_id, to_email, subject, body, created_at)
        VALUES (?,?,?,?,?)
    """, (appt.get("lead_id"), appt.get("client_email"), subject, body, now))
    draft_id = cursor.lastrowid
    conn.commit()

    gmail_draft_id = None
    creds = gm.get_credentials()
    if creds and appt.get("client_email"):
        try:
            gmail_draft_id = gm.create_gmail_draft_public(
                creds, appt["client_email"], subject, body,
                thread_id=appt.get("thread_id"),
            )
            conn.execute("UPDATE drafts SET gmail_draft_id=? WHERE id=?", (gmail_draft_id, draft_id))
            conn.commit()
        except Exception as e:
            print(f"[ai] Gmail draft push failed for availability options: {e}")
    conn.close()

    return {"ok": True, "draft_id": draft_id, "gmail_draft_id": gmail_draft_id, "subject": subject, "body": body}


def draft_alternative_times(appointment_id: int) -> dict:
    """
    Claude drafts a reply suggesting 2-3 alternative meeting times
    based on the agent's availability windows and the blocked proposed time.
    Saves as a local draft and pushes to Gmail if connected.
    """
    import json as _json
    import datetime as _dt

    conn = get_conn()
    appt = conn.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
    cfg  = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM config").fetchall()}
    conn.close()

    if not appt:
        raise ValueError(f"Appointment {appointment_id} not found")
    appt = dict(appt)

    profile   = get_agent_profile()
    agent_name = profile.get("agent_name", "Your Agent")
    timezone  = cfg.get("timezone", "America/Los_Angeles")
    avail_raw = cfg.get("availability_windows")

    avail_text = "weekdays 9am–6pm"
    if avail_raw:
        try:
            windows = _json.loads(avail_raw)
            enabled = [w for w in windows if w.get("enabled")]
            DAY_SHORT = {"monday":"Mon","tuesday":"Tue","wednesday":"Wed",
                         "thursday":"Thu","friday":"Fri","saturday":"Sat","sunday":"Sun"}
            if enabled:
                avail_text = ", ".join(
                    f"{DAY_SHORT.get(w['day'], w['day'])} {w['start']}–{w['end']}"
                    for w in enabled
                )
        except Exception:
            pass

    sig_enabled = profile.get("agent_signature_enabled", "false") == "true"
    signature   = profile.get("agent_signature", "").strip() if sig_enabled else ""
    today_str   = _dt.datetime.now().strftime("%A, %B %d, %Y")

    proposed = appt.get("proposed_date_text") or appt.get("proposed_datetime") or "the proposed time"

    prompt = f"""You are {agent_name}, a real estate agent. The proposed meeting time doesn't work and you need to suggest alternatives.

Proposed time that doesn't work: {proposed}
Your availability ({timezone}): {avail_text}
Today: {today_str}

Write a SHORT, warm reply suggesting 2-3 SPECIFIC alternative days and times in the next 1–2 weeks that fall within your availability. Be friendly, not stiff.

Rules:
- 2–3 short paragraphs, under 100 words total
- One brief apology for the conflict
- Suggest 2–3 specific options like "Tuesday March 5th at 10am or Thursday March 7th at 2pm"
- End with a simple "let me know what works" close
- No subject line, no signature, plain text only"""

    response = _claude().messages.create(
        model="claude-sonnet-4-5",
        max_tokens=250,
        messages=[{"role": "user", "content": prompt}],
    )

    body = response.content[0].text.strip()
    if signature:
        body = body + "\n\n" + signature

    subject = f"Re: {(appt.get('context_snippet') or 'Our Appointment')[:60]}"
    now     = _dt.datetime.utcnow().isoformat() + "Z"

    conn = get_conn()
    cursor = conn.execute("""
        INSERT INTO drafts (lead_id, to_email, subject, body, created_at)
        VALUES (?,?,?,?,?)
    """, (appt.get("lead_id"), appt.get("client_email"), subject, body, now))
    draft_id = cursor.lastrowid
    conn.commit()

    gmail_draft_id = None
    creds = gm.get_credentials()
    if creds and appt.get("client_email"):
        try:
            gmail_draft_id = gm.create_gmail_draft_public(
                creds, appt["client_email"], subject, body,
                thread_id=appt.get("thread_id"),
            )
            conn.execute(
                "UPDATE drafts SET gmail_draft_id=? WHERE id=?",
                (gmail_draft_id, draft_id)
            )
            conn.commit()
        except Exception as e:
            print(f"[ai] Gmail draft push failed for alt-times: {e}")
    conn.close()

    return {
        "ok": True,
        "draft_id": draft_id,
        "gmail_draft_id": gmail_draft_id,
        "subject": subject,
        "body": body,
    }


def build_confirmation_email(appointment: dict, profile: dict) -> str:
    """
    Build the brief confirmation email body (no subject, no salutation header).
    e.g. "I've scheduled you for Tuesday March 5th at 10am at 742 Anacapa St.
    Looking forward to seeing you [and Partner]. Let me know if you have any questions."
    """
    name    = appointment.get("client_name") or "you"
    partner = appointment.get("partner_name")
    dt_text = appointment.get("proposed_date_text") or appointment.get("proposed_datetime") or "the scheduled time"
    address = appointment.get("proposed_address")
    mtype   = appointment.get("meeting_type", "appointment")

    location_str = f" at {address}" if address else ""
    seeing_str   = f" and {partner}" if partner else ""

    body = (
        f"I've scheduled {mtype_label(mtype)} for {dt_text}{location_str}. "
        f"Looking forward to seeing you{seeing_str}. "
        f"Let me know if you have any questions or concerns."
    )

    sig_enabled = profile.get("agent_signature_enabled", "false") == "true"
    signature   = profile.get("agent_signature", "").strip() if sig_enabled else ""
    if signature:
        from gmail import strip_html
        body = body + "\n\n" + strip_html(signature)

    return body


def mtype_label(mtype: str) -> str:
    labels = {
        "showing":    "a showing",
        "call":       "a call",
        "open_house": "an open house visit",
        "coffee":     "a coffee meeting",
        "other":      "an appointment",
    }
    return labels.get(mtype or "other", "an appointment")


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

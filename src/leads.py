"""
leads.py — Pydantic lead model, email parser, and dedup logic.
"""

import re
import hashlib
import datetime
from typing import Optional
from pydantic import BaseModel


class Lead(BaseModel):
    source:              str = "gmail"
    from_email:          str
    name:                Optional[str] = None
    phone:               Optional[str] = None
    subject:             Optional[str] = None
    body_excerpt:        Optional[str] = None
    budget_monthly_usd:  Optional[int] = None
    first_seen_at:       str
    fingerprint:         str
    gmail_msg_id:        Optional[str] = None


def make_fingerprint(email: str, phone: str = "") -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def utc_now() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def parse_email_to_lead(headers: dict, body: str, msg_id: str = None) -> Lead:
    """
    Parse a raw Gmail message into a Lead.
    headers: dict of header name → value (From, Subject, Date, etc.)
    body:    decoded plain-text body
    """
    from_raw   = headers.get("From", "")
    subject    = headers.get("Subject", "")

    # Extract email address from "Name <email@domain.com>"
    email_m = re.search(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", from_raw)
    from_email = email_m.group(0).lower() if email_m else from_raw.strip().lower()

    # Extract display name
    name_m = re.match(r'^"?([^"<@\n]{2,}?)"?\s*<', from_raw)
    name = name_m.group(1).strip() if name_m else None

    # Look for explicit Name: field in body (fixture-style emails)
    body_name_m = re.search(r"^Name\s*:\s*(.+)$", body, re.MULTILINE | re.IGNORECASE)
    if body_name_m and not name:
        name = body_name_m.group(1).strip()

    # Phone — US format
    phone_m = re.search(r"(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})", body)
    phone = phone_m.group(1) if phone_m else None

    # Monthly budget
    budget = None
    budget_m = re.search(
        r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per\s*month|/mo\b|/month\b)",
        body, re.IGNORECASE,
    )
    if budget_m:
        budget = int(budget_m.group(1).replace(",", ""))

    fp = make_fingerprint(from_email, phone or "")

    return Lead(
        source="gmail" if msg_id else "fixture",
        from_email=from_email,
        name=name,
        phone=phone,
        subject=subject,
        body_excerpt=body.strip()[:600],
        budget_monthly_usd=budget,
        first_seen_at=utc_now(),
        fingerprint=fp,
        gmail_msg_id=msg_id,
    )

#!/usr/bin/env python3
"""
seed_test_threads.py — Create realistic email threads for all pending appointment types.

Inserts directly into the DB (no real Gmail needed). Covers:
  A) Confirmed appointment — client confirms a specific time (pending: needs Accept)
  B) Availability inquiry — client asks "when are you free?" (pending: needs Suggest Times)
  C) Mutual confirmation — back-and-forth ending in both sides agreeing (pending: needs Accept)
  D) Open house inquiry — client asks about a specific open house day (pending: inquiry)

Run:
  docker exec -it lucilease python /scripts/seed_test_threads.py

Clears all existing appointments first for a clean slate.
"""

import sqlite3
import datetime
import random
import string
import os

DB_PATH = os.environ.get("DB_PATH", "/data/lucilease.db")

def rand_id(n=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def dt_ago(days=0, hours=0, minute=0):
    t = datetime.datetime.utcnow() - datetime.timedelta(days=days, hours=hours)
    return t.replace(minute=minute, second=0, microsecond=0).isoformat() + "Z"

def insert_lead(cur, *, from_email, name, subject, body, phone=None, budget=None,
                days_ago=3, hour=10, thread_id=None, status="new"):
    fp = f"seed_{rand_id(16)}"
    tid = thread_id or f"thread_{rand_id(12)}"
    ts = dt_ago(days=days_ago, hours=(10 - hour))
    cur.execute("""
        INSERT OR IGNORE INTO leads
          (fingerprint, gmail_msg_id, gmail_thread_id, from_email, name, subject,
           body_excerpt, body_full, phone, budget_monthly_usd, status, first_seen_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (fp, f"msg_{rand_id()}", tid, from_email, name, subject,
          body[:300], body, phone, budget, status, ts))
    return cur.lastrowid, tid

def insert_appt(cur, *, lead_id, thread_id, meeting_type, status="pending",
                proposed_datetime=None, proposed_date_text=None, proposed_address=None,
                client_name=None, client_email=None, partner_name=None, context_snippet=None,
                source="inbox"):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    cur.execute("""
        INSERT INTO appointments
          (lead_id, thread_id, status, meeting_type,
           proposed_datetime, proposed_date_text, proposed_address,
           client_name, client_email, partner_name, context_snippet,
           source, detected_at, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (lead_id, thread_id, status, meeting_type,
          proposed_datetime, proposed_date_text, proposed_address,
          client_name, client_email, partner_name, context_snippet,
          source, now, now, now))
    return cur.lastrowid

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── Clear existing appointments ──────────────────────────────────────────
    cur.execute("DELETE FROM appointments")
    print("🗑  Cleared all existing appointments\n")

    now = datetime.datetime.utcnow()
    next_sat = now + datetime.timedelta(days=(5 - now.weekday() + 7) % 7 + 1)
    next_sat = next_sat.replace(hour=11, minute=0, second=0, microsecond=0)
    next_sun = now + datetime.timedelta(days=(6 - now.weekday() + 7) % 7 + 1)
    next_sun = next_sun.replace(hour=14, minute=0, second=0, microsecond=0)

    # ── Scenario A: violettxoxo — confirmed showing, 742 Anacapa ─────────────
    thread_a = f"thread_a_{rand_id(8)}"
    print("Scenario A: violettxoxo — confirmed showing, 742 Anacapa St (Sat 11am)")

    lead_a1, _ = insert_lead(cur,
        from_email="violettxoxo0@gmail.com", name="Violet",
        subject="Interested in 742 Anacapa St", thread_id=thread_a,
        body="""Hi,

I saw your listing for 742 Anacapa and I'm really interested — the location looks perfect for me and my partner Marco. We're looking to move in next month, budget around $3,200/mo.

Could we schedule a showing this week? Pretty flexible on timing.

— Violet""",
        phone="805-555-0142", budget=3200, days_ago=5, hour=9)

    insert_lead(cur,
        from_email="violettxoxo0@gmail.com", name="Violet",
        subject="Re: Interested in 742 Anacapa St", thread_id=thread_a,
        body="""Saturday at 11am works perfectly for us! Marco and I will be there.

Just confirming the address is 742 Anacapa St, Santa Barbara?

Thanks so much — Violet""",
        days_ago=3, hour=10, status="handled")

    insert_appt(cur,
        lead_id=lead_a1, thread_id=thread_a,
        meeting_type="showing", status="pending",
        proposed_datetime=next_sat.isoformat() + "Z",
        proposed_date_text=next_sat.strftime("Saturday, %B %-d at 11:00 AM"),
        proposed_address="742 Anacapa St, Santa Barbara, CA",
        client_name="Violet", client_email="violettxoxo0@gmail.com", partner_name="Marco",
        context_snippet="Saturday at 11am works perfectly for us! Marco and I will be there.")
    print(f"  ✓ thread={thread_a} | {next_sat.strftime('%a %b %-d at %-I:%M %p')} → ✅ Accept")

    # ── Scenario B: violettxoxo — availability inquiry, 88 Harbor Way ────────
    thread_b = f"thread_b_{rand_id(8)}"
    print("Scenario B: violettxoxo — availability inquiry, 88 Harbor Way")

    lead_b1, _ = insert_lead(cur,
        from_email="violettxoxo0@gmail.com", name="Violet",
        subject="88 Harbor Way — when can we view?", thread_id=thread_b,
        body="""Hello,

I also noticed 88 Harbor Way in your listings — it looks stunning and I'd love to see it in person.

When are you available for showings? I'm free most weekday afternoons and anytime on weekends.

— Violet""",
        phone="805-555-0142", budget=5500, days_ago=2, hour=13)

    insert_appt(cur,
        lead_id=lead_b1, thread_id=thread_b,
        meeting_type="availability_inquiry", status="pending",
        proposed_address="88 Harbor Way, Santa Barbara, CA",
        client_name="Violet", client_email="violettxoxo0@gmail.com",
        context_snippet="When are you available for showings? Free weekday afternoons and weekends.")
    print(f"  ✓ thread={thread_b} | inquiry → 📅 Suggest Times")

    # ── Scenario C: nathan.trudeau — confirmed showing, 1405 Cliff Dr ────────
    thread_c = f"thread_c_{rand_id(8)}"
    print("Scenario C: nathan.trudeau — confirmed showing, 1405 Cliff Dr (Sun 2pm)")

    lead_c1, _ = insert_lead(cur,
        from_email="nathan.trudeau@gmail.com", name="Nathan",
        subject="Inquiry: 1405 Cliff Dr", thread_id=thread_c,
        body="""Hi,

I came across 1405 Cliff Dr and it looks like exactly what I've been searching for — the views are incredible. Budget is flexible, up to $4,500/mo.

Any chance we could arrange a private showing this weekend?

Thanks, Nathan""",
        phone="805-555-0199", budget=4500, days_ago=6, hour=10, status="handled")

    insert_lead(cur,
        from_email="nathan.trudeau@gmail.com", name="Nathan",
        subject="Re: Inquiry: 1405 Cliff Dr", thread_id=thread_c,
        body="""Sunday at 2pm works perfectly for me. See you then!

Looking forward to it — I've already looked at the floor plan twice haha.

Nathan""",
        days_ago=4, hour=16, status="handled")

    insert_appt(cur,
        lead_id=lead_c1, thread_id=thread_c,
        meeting_type="showing", status="pending",
        proposed_datetime=next_sun.isoformat() + "Z",
        proposed_date_text=next_sun.strftime("Sunday, %B %-d at 2:00 PM"),
        proposed_address="1405 Cliff Dr, Santa Barbara, CA",
        client_name="Nathan", client_email="nathan.trudeau@gmail.com",
        context_snippet="Sunday at 2pm works perfectly for me. See you then!")
    print(f"  ✓ thread={thread_c} | {next_sun.strftime('%a %b %-d at %-I:%M %p')} → ✅ Accept")

    # ── Scenario D: nathan.trudeau — open house inquiry, 742 Anacapa ─────────
    thread_d = f"thread_d_{rand_id(8)}"
    print("Scenario D: nathan.trudeau — open house inquiry, 742 Anacapa St")

    lead_d1, _ = insert_lead(cur,
        from_email="nathan.trudeau@gmail.com", name="Nathan",
        subject="Open house info — 742 Anacapa?", thread_id=thread_d,
        body="""Hello,

I noticed 742 Anacapa St is listed and I'm very interested. Do you have any open house events coming up, or can we set up a private tour?

I'm available most mornings and Saturday afternoons. Budget around $3,200/mo.

Thanks, Nathan""",
        phone="805-555-0199", budget=3200, days_ago=1, hour=15)

    insert_appt(cur,
        lead_id=lead_d1, thread_id=thread_d,
        meeting_type="availability_inquiry", status="pending",
        proposed_address="742 Anacapa St, Santa Barbara, CA",
        client_name="Nathan", client_email="nathan.trudeau@gmail.com",
        context_snippet="Any open house events coming up? Available mornings and Saturday afternoons.")
    print(f"  ✓ thread={thread_d} | inquiry → 📅 Suggest Times")

    conn.commit()
    conn.close()

    print("""
✅ Done! 4 scenarios seeded using your two test emails.
Refresh the dashboard — Pending Appointments should show:

  [A] violettxoxo — 🏠 Showing · 742 Anacapa · Sat 11am  → ✅ Accept [AI]
  [B] violettxoxo — 🗓 Inquiry · 88 Harbor Way           → 📅 Suggest Times [AI]
  [C] nathan.trudeau — 🏠 Showing · 1405 Cliff Dr · Sun 2pm → ✅ Accept [AI]
  [D] nathan.trudeau — 🗓 Inquiry · 742 Anacapa           → 📅 Suggest Times [AI]

Accepting A or C will send a real confirmation email to those addresses.
Suggest Times on B or D will draft available slots to those addresses.
""")

if __name__ == "__main__":
    main()

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

    # ── Scenario A: Client confirms a specific time ──────────────────────────
    # Full back-and-forth: Vi reaches out → agent proposes time → Vi confirms
    thread_a = f"thread_a_{rand_id(8)}"
    print("Creating Scenario A: Confirmed appointment — Vi + Marco, 742 Anacapa")

    lead_a1, _ = insert_lead(cur,
        from_email="violettxoxo@gmail.com", name="Vi Rosario",
        subject="Interested in 742 Anacapa St", thread_id=thread_a,
        body="""Hi there,

I came across your listing for 742 Anacapa St and I'm really interested — the location is perfect for me and my partner Marco. We're looking to move in sometime next month.

Would it be possible to schedule a showing sometime this week? We're pretty flexible. Budget is around $3,200/month.

Best, Vi""",
        phone="805-555-0142", budget=3200, days_ago=5, hour=9)

    # Agent reply (not a real lead, just context — simulate as handled lead in same thread)
    lead_a2, _ = insert_lead(cur,
        from_email="violettxoxo@gmail.com", name="Vi Rosario",
        subject="Re: Interested in 742 Anacapa St", thread_id=thread_a,
        body="""Hi Vi,

Great to hear from you! I'd love to show you 742 Anacapa. How does Saturday March 8th at 11:00 AM work for you and Marco?

Looking forward to it!""",
        days_ago=4, hour=14, status="handled")

    # Vi confirms
    lead_a3, _ = insert_lead(cur,
        from_email="violettxoxo@gmail.com", name="Vi Rosario",
        subject="Re: Interested in 742 Anacapa St", thread_id=thread_a,
        body="""Saturday March 8th at 11am works perfectly for us! Marco and I will be there.

742 Anacapa St, right? Just want to confirm the address. So excited to see it!

Thanks, Vi""",
        days_ago=3, hour=10, status="handled")

    next_sat = datetime.datetime.utcnow() + datetime.timedelta(days=(5 - datetime.datetime.utcnow().weekday() + 7) % 7 + 1)
    next_sat = next_sat.replace(hour=11, minute=0, second=0, microsecond=0)

    appt_a = insert_appt(cur,
        lead_id=lead_a1, thread_id=thread_a,
        meeting_type="showing", status="pending",
        proposed_datetime=next_sat.isoformat() + "Z",
        proposed_date_text=next_sat.strftime("Saturday, %B %-d at 11:00 AM"),
        proposed_address="742 Anacapa St, Santa Barbara, CA",
        client_name="Vi Rosario", client_email="violettxoxo@gmail.com",
        partner_name="Marco",
        context_snippet="Saturday at 11am works perfectly for us! Marco and I will be there.")
    print(f"  ✓ Scenario A inserted — appt id={appt_a}, thread={thread_a}")
    print(f"    Proposed: {next_sat.strftime('%A %b %-d at %-I:%M %p')}")

    # ── Scenario B: Availability inquiry — client asks about times ───────────
    thread_b = f"thread_b_{rand_id(8)}"
    print("\nCreating Scenario B: Availability inquiry — Mia Chen, 1405 Cliff Dr")

    lead_b1, _ = insert_lead(cur,
        from_email="mia.chen.sb@gmail.com", name="Mia Chen",
        subject="Question about 1405 Cliff Dr", thread_id=thread_b,
        body="""Hello,

I saw 1405 Cliff Dr on Zillow and it looks stunning — exactly what I've been looking for. I'd love to arrange a viewing.

When are you available for showings? I'm flexible most weekdays after 11am and any time on weekends.

Thanks, Mia""",
        phone="805-555-0201", budget=4200, days_ago=2, hour=11)

    appt_b = insert_appt(cur,
        lead_id=lead_b1, thread_id=thread_b,
        meeting_type="availability_inquiry", status="pending",
        proposed_address="1405 Cliff Dr, Santa Barbara, CA",
        client_name="Mia Chen", client_email="mia.chen.sb@gmail.com",
        context_snippet="When are you available for showings? Flexible weekdays after 11am and weekends.")
    print(f"  ✓ Scenario B inserted — appt id={appt_b}, thread={thread_b}")
    print(f"    Type: availability_inquiry — use '📅 Suggest Times [AI]'")

    # ── Scenario C: Back-and-forth leading to mutual agreement ───────────────
    thread_c = f"thread_c_{rand_id(8)}"
    print("\nCreating Scenario C: Mutual agreement — Derek Hoffman, 88 Harbor Way")

    lead_c1, _ = insert_lead(cur,
        from_email="d.hoffman.realty@gmail.com", name="Derek Hoffman",
        subject="Interested in 88 Harbor Way", thread_id=thread_c,
        body="""Hi,

I'm very interested in 88 Harbor Way. My wife and I have been searching for a waterfront property for months and this one checks all our boxes.

Can we set up a showing this weekend?

Best, Derek""",
        phone="805-555-0333", budget=5800, days_ago=6, hour=8, status="handled")

    lead_c2, _ = insert_lead(cur,
        from_email="d.hoffman.realty@gmail.com", name="Derek Hoffman",
        subject="Re: Interested in 88 Harbor Way", thread_id=thread_c,
        body="""Sunday works great. We'll be there at 2pm.

Looking forward to it — we're very serious about this one.

Derek & Lisa""",
        days_ago=5, hour=16, status="handled")

    # Agent reply confirming
    lead_c3, _ = insert_lead(cur,
        from_email="d.hoffman.realty@gmail.com", name="Derek Hoffman",
        subject="Re: Interested in 88 Harbor Way", thread_id=thread_c,
        body="""Perfect. See you Sunday at 2pm at 88 Harbor Way. 

We're both free and very excited — Lisa has already looked at the floor plan!

Thanks again, Derek""",
        days_ago=4, hour=9, status="handled")

    next_sun = datetime.datetime.utcnow() + datetime.timedelta(days=(6 - datetime.datetime.utcnow().weekday() + 7) % 7 + 1)
    next_sun = next_sun.replace(hour=14, minute=0, second=0, microsecond=0)

    appt_c = insert_appt(cur,
        lead_id=lead_c1, thread_id=thread_c,
        meeting_type="showing", status="pending",
        proposed_datetime=next_sun.isoformat() + "Z",
        proposed_date_text=next_sun.strftime("Sunday, %B %-d at 2:00 PM"),
        proposed_address="88 Harbor Way, Santa Barbara, CA",
        client_name="Derek Hoffman", client_email="d.hoffman.realty@gmail.com",
        partner_name="Lisa",
        context_snippet="See you Sunday at 2pm at 88 Harbor Way — both very excited.")
    print(f"  ✓ Scenario C inserted — appt id={appt_c}, thread={thread_c}")
    print(f"    Proposed: {next_sun.strftime('%A %b %-d at %-I:%M %p')}")

    # ── Scenario D: Open house inquiry ───────────────────────────────────────
    thread_d = f"thread_d_{rand_id(8)}"
    print("\nCreating Scenario D: Open house inquiry — James Whitfield, 742 Anacapa")

    lead_d1, _ = insert_lead(cur,
        from_email="j.whitfield.homes@gmail.com", name="James Whitfield",
        subject="Open house at 742 Anacapa?", thread_id=thread_d,
        body="""Hello,

I noticed 742 Anacapa St is listed. Do you have any open house dates scheduled? Or could we arrange a private showing if not?

I'm available most weekday mornings and Saturday afternoons. Budget is up to $3,500/month.

Thanks, James""",
        phone="805-555-0444", budget=3500, days_ago=1, hour=14)

    appt_d = insert_appt(cur,
        lead_id=lead_d1, thread_id=thread_d,
        meeting_type="availability_inquiry", status="pending",
        proposed_address="742 Anacapa St, Santa Barbara, CA",
        client_name="James Whitfield", client_email="j.whitfield.homes@gmail.com",
        context_snippet="Do you have any open house dates? Available weekday mornings and Saturday afternoons.")
    print(f"  ✓ Scenario D inserted — appt id={appt_d}, thread={thread_d}")
    print(f"    Type: availability_inquiry — use '📅 Suggest Times [AI]'")

    conn.commit()
    conn.close()

    print("""
✅ Done! All 4 scenarios created. Refresh the Lucilease dashboard.

Pending Appointments panel should show:

  [A] 🏠 Showing — Vi Rosario & Marco
      Saturday at 11:00 AM · 742 Anacapa St
      → ✅ Accept [AI] to confirm + send email

  [B] 🗓 Availability Inquiry — Mia Chen
      1405 Cliff Dr — asking about your available times
      → 📅 Suggest Times [AI] to draft open slots

  [C] 🏠 Showing — Derek Hoffman & Lisa
      Sunday at 2:00 PM · 88 Harbor Way
      → ✅ Accept [AI] to confirm + send email

  [D] 🗓 Availability Inquiry — James Whitfield
      742 Anacapa St — asking about open house dates
      → 📅 Suggest Times [AI] to draft open slots
""")

if __name__ == "__main__":
    main()

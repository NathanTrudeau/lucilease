#!/usr/bin/env python3
"""
seed_appointment_threads.py — Inject realistic appointment confirmation email threads
into the Lucilease SQLite DB for testing the appointment detection pipeline.

Creates two scenarios:
  A) violettxoxo0@gmail.com — Vi + Marco, Saturday 11am showing at 742 Anacapa.
     Pending: client confirmed, agent needs to Accept.
  B) nathan.trudeau@gmail.com — Sunday 2pm showing at 1405 Cliff Dr.
     Pending: needs agent Accept.

Run inside the container:
  docker exec -it lucilease python /scripts/seed_appointment_threads.py
"""

import sqlite3
import datetime
import random
import string
import os

DB_PATH = os.environ.get("DB_PATH", "/data/lucilease.db")

def rand_id(n=12):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def ts(days_ago=0, hour=10, minute=0):
    dt = datetime.datetime.utcnow() - datetime.timedelta(days=days_ago)
    dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return dt.isoformat() + "Z"

def insert_lead(cur, *, msg_id, thread_id, from_email, name, subject,
                body_excerpt, body_full, phone, budget=None, first_seen_at, status="new"):
    fp = f"seed_{msg_id}"
    cur.execute("""
        INSERT OR IGNORE INTO leads (
            fingerprint, gmail_msg_id, gmail_thread_id,
            from_email, name, subject, body_excerpt, body_full,
            phone, budget_monthly_usd, status, first_seen_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (fp, msg_id, thread_id, from_email, name, subject,
          body_excerpt, body_full, phone, budget, status, first_seen_at))
    return cur.lastrowid

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    now = datetime.datetime.utcnow()

    # ── Scenario A: Vi Rosario (violettxoxo) — client confirms ───────────────
    thread_a = f"thread_appt_a_{rand_id(6)}"
    print("Creating Scenario A: violettxoxo0@gmail.com — client confirms Saturday showing")

    lead_a_id = insert_lead(cur,
        msg_id=f"msg_a1_{rand_id()}",
        thread_id=thread_a,
        from_email="violettxoxo0@gmail.com",
        name="Vi Rosario",
        subject="Interested in 742 Anacapa St",
        body_excerpt="Hi! I saw the listing for 742 Anacapa and I'd love to schedule a showing...",
        body_full="""Hi there,

I came across your listing for 742 Anacapa St and I'm really interested — the location is perfect for me and my partner Marco.

Would it be possible to schedule a showing sometime this week or next? We're pretty flexible on timing. Budget is around $3,200/month.

Looking forward to hearing from you!

Best,
Vi""",
        phone="805-555-0142",
        budget=3200,
        first_seen_at=ts(days_ago=4, hour=9, minute=14),
    )

    # Vi's confirmation reply
    insert_lead(cur,
        msg_id=f"msg_a3_{rand_id()}",
        thread_id=thread_a,
        from_email="violettxoxo0@gmail.com",
        name="Vi Rosario",
        subject="Re: Interested in 742 Anacapa St",
        body_excerpt="Saturday at 11am works perfectly for us! Marco and I will be there.",
        body_full="""Hi,

Saturday at 11am works perfectly for us! Marco and I will be there.

742 Anacapa St, right? Just want to confirm the address.

Thanks so much,
Vi""",
        phone="805-555-0142",
        first_seen_at=ts(days_ago=2, hour=14, minute=33),
        status="handled",
    )

    next_saturday = now + datetime.timedelta(days=(5 - now.weekday() + 7) % 7 + 1)
    next_saturday = next_saturday.replace(hour=11, minute=0, second=0, microsecond=0)

    now_iso = ts(days_ago=0)
    cur.execute("""
        INSERT INTO appointments (
            lead_id, thread_id, status, meeting_type,
            proposed_datetime, proposed_date_text,
            proposed_address, client_name, client_email, partner_name,
            context_snippet, source, detected_at, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        lead_a_id, thread_a, "pending", "showing",
        next_saturday.isoformat() + "Z",
        next_saturday.strftime("Saturday, %B %d at 11:00 AM"),
        "742 Anacapa St, Santa Barbara, CA",
        "Vi Rosario", "violettxoxo0@gmail.com", "Marco",
        "Saturday at 11am works perfectly for us! Marco and I will be there.",
        "inbox",
        ts(days_ago=2, hour=14, minute=45),
        now_iso,
    ))

    print(f"  ✓ Lead A inserted (id={lead_a_id}), thread={thread_a}")
    print(f"  ✓ Appointment A — pending, {next_saturday.strftime('%A %b %d at %I:%M %p')}")

    # ── Scenario B: Nathan test account — awaiting agent accept ──────────────
    thread_b = f"thread_appt_b_{rand_id(6)}"
    print("\nCreating Scenario B: nathan.trudeau@gmail.com — needs your Accept")

    lead_b_id = insert_lead(cur,
        msg_id=f"msg_b1_{rand_id()}",
        thread_id=thread_b,
        from_email="nathan.trudeau@gmail.com",
        name="Nathan T. (test)",
        subject="Question about 1405 Cliff Dr",
        body_excerpt="Hey, I'm interested in 1405 Cliff Dr. Any open house slots available?",
        body_full="""Hey,

I've been looking at 1405 Cliff Dr — it looks incredible. Are there any open house slots available this weekend, or could we arrange a private showing?

Budget is flexible, around $4,500/month if it's worth it.

Cheers,
Nathan""",
        phone="805-555-0199",
        budget=4500,
        first_seen_at=ts(days_ago=5, hour=11, minute=2),
    )

    insert_lead(cur,
        msg_id=f"msg_b3_{rand_id()}",
        thread_id=thread_b,
        from_email="nathan.trudeau@gmail.com",
        name="Nathan T. (test)",
        subject="Re: Question about 1405 Cliff Dr",
        body_excerpt="Perfect, Sunday at 2pm works great. See you then!",
        body_full="""Perfect, Sunday at 2pm works great. See you then!

Looking forward to it.

— Nathan""",
        phone="805-555-0199",
        first_seen_at=ts(days_ago=3, hour=16, minute=20),
        status="handled",
    )

    next_sunday = now + datetime.timedelta(days=(6 - now.weekday() + 7) % 7 + 1)
    next_sunday = next_sunday.replace(hour=14, minute=0, second=0, microsecond=0)

    cur.execute("""
        INSERT INTO appointments (
            lead_id, thread_id, status, meeting_type,
            proposed_datetime, proposed_date_text,
            proposed_address, client_name, client_email,
            context_snippet, source, detected_at, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        lead_b_id, thread_b, "pending", "showing",
        next_sunday.isoformat() + "Z",
        next_sunday.strftime("Sunday, %B %d at 2:00 PM"),
        "1405 Cliff Dr, Santa Barbara, CA",
        "Nathan T. (test)", "nathan.trudeau@gmail.com",
        "Perfect, Sunday at 2pm works great. See you then!",
        "inbox",
        ts(days_ago=3, hour=16, minute=30),
        now_iso,
    ))

    print(f"  ✓ Lead B inserted (id={lead_b_id}), thread={thread_b}")
    print(f"  ✓ Appointment B — pending, {next_sunday.strftime('%A %b %d at %I:%M %p')}")

    conn.commit()
    conn.close()

    print("\n✅ Done! Refresh the Lucilease dashboard to see:")
    print("   A) Vi Rosario (violettxoxo) — Saturday 11am, 742 Anacapa → click ✅ Accept [AI]")
    print("   B) Nathan T. (test) — Sunday 2pm, 1405 Cliff Dr → click ✅ Accept [AI]")
    print("   Both show ⏳ Pending in the Recent Leads appointment column.")

if __name__ == "__main__":
    main()

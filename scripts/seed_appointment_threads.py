#!/usr/bin/env python3
"""
seed_appointment_threads.py — Inject realistic appointment confirmation email threads
into the Lucilease SQLite DB for testing the appointment detection pipeline.

Creates two scenarios:
  A) Thread from violettxoxo@gmail.com → full back-and-forth → CLIENT confirms.
     Lucilease should auto-detect and create a "pending" appointment awaiting agent accept.
  B) Thread from trudeau.nathan@gmail.com → back-and-forth → AGENT confirms.
     Shows as accepted on dashboard (agent already said yes).

Run inside the container:
  docker exec -it lucilease python /scripts/seed_appointment_threads.py
Or from host if DB is accessible:
  python scripts/seed_appointment_threads.py
"""

import sqlite3
import datetime
import random
import string
import sys
import os

DB_PATH = os.environ.get("DB_PATH", "/data/lucilease.db")

def rand_id(n=12):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def ts(days_ago=0, hour=10, minute=0):
    dt = datetime.datetime.utcnow() - datetime.timedelta(days=days_ago)
    dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return dt.isoformat() + "Z"

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    now = datetime.datetime.utcnow()

    # ── Scenario A: Client confirms (violettxoxo) ─────────────────────────────
    # Thread: Vi reaches out → agent responds → Vi confirms Saturday
    thread_a = f"thread_appt_a_{rand_id(6)}"
    lead_a_id = None

    print("Creating Scenario A: violettxoxo@gmail.com — client confirms Saturday showing")

    cur.execute("""
        INSERT INTO leads (
            gmail_message_id, gmail_thread_id, from_email, name, subject,
            body_excerpt, body_full, phone, budget_monthly_usd,
            first_seen_at, is_handled
        ) VALUES (?,?,?,?,?,?,?,?,?,?,0)
    """, (
        f"msg_a1_{rand_id()}", thread_a,
        "violettxoxo@gmail.com", "Vi Rosario",
        "Interested in 742 Anacapa St",
        "Hi! I saw the listing for 742 Anacapa and I'd love to schedule a showing...",
        """Hi there,

I came across your listing for 742 Anacapa St and I'm really interested — the location is perfect for me and my partner Marco.

Would it be possible to schedule a showing sometime this week or next? We're pretty flexible on timing. Budget is around $3,200/month.

Looking forward to hearing from you!

Best,
Vi""",
        "805-555-0142", 3200,
        ts(days_ago=4, hour=9, minute=14),
    ))
    lead_a_id = cur.lastrowid

    # Agent reply (day 3)
    # We simulate this as context in the thread — stored as a second "lead" row with same thread_id
    # (In reality the agent reply comes from Gmail sent; we store it as a thread message)

    # Vi's confirmation reply (day 2)
    cur.execute("""
        INSERT INTO leads (
            gmail_message_id, gmail_thread_id, from_email, name, subject,
            body_excerpt, body_full, phone,
            first_seen_at, is_handled
        ) VALUES (?,?,?,?,?,?,?,?,?,1)
    """, (
        f"msg_a3_{rand_id()}", thread_a,
        "violettxoxo@gmail.com", "Vi Rosario",
        "Re: Interested in 742 Anacapa St",
        "Saturday at 11am works perfectly for us! Marco and I will be there.",
        """Hi,

Saturday at 11am works perfectly for us! Marco and I will be there.

742 Anacapa St, right? Just want to confirm the address.

Thanks so much,
Vi""",
        "805-555-0142",
        ts(days_ago=2, hour=14, minute=33),
    ))

    # Insert pending appointment for Scenario A
    next_saturday = now + datetime.timedelta(days=(5 - now.weekday() + 7) % 7 + 1)
    next_saturday = next_saturday.replace(hour=11, minute=0, second=0, microsecond=0)

    cur.execute("""
        INSERT INTO appointments (
            lead_id, thread_id, status, meeting_type,
            proposed_datetime, proposed_date_text,
            proposed_address, client_name, client_email, partner_name,
            context_snippet, source, detected_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        lead_a_id, thread_a, "pending", "showing",
        next_saturday.isoformat() + "Z",
        next_saturday.strftime("Saturday, %B %d at 11:00 AM"),
        "742 Anacapa St, Santa Barbara, CA",
        "Vi Rosario", "violettxoxo@gmail.com", "Marco",
        "Saturday at 11am works perfectly for us! Marco and I will be there.",
        "inbox",
        ts(days_ago=2, hour=14, minute=45),
    ))

    print(f"  ✓ Lead A inserted (id={lead_a_id}), thread={thread_a}")
    print(f"  ✓ Appointment A inserted — status=pending, {next_saturday.strftime('%A %b %d at %I:%M %p')}")

    # ── Scenario B: Agent confirms (trudeau.nathan) — needs agent to accept ──
    # Thread: Nathan's test contact reaches out about open house → agent says "yes come by Saturday 2pm" → client says "Perfect, see you then"
    thread_b = f"thread_appt_b_{rand_id(6)}"
    lead_b_id = None

    print("\nCreating Scenario B: trudeau.nathan@gmail.com — back-and-forth, awaiting your accept")

    cur.execute("""
        INSERT INTO leads (
            gmail_message_id, gmail_thread_id, from_email, name, subject,
            body_excerpt, body_full, phone, budget_monthly_usd,
            first_seen_at, is_handled
        ) VALUES (?,?,?,?,?,?,?,?,?,?,0)
    """, (
        f"msg_b1_{rand_id()}", thread_b,
        "trudeau.nathan@gmail.com", "Nathan T. (test)",
        "Question about 1405 Cliff Dr",
        "Hey, I'm interested in 1405 Cliff Dr. Any open house slots available?",
        """Hey,

I've been looking at 1405 Cliff Dr on the listing — it looks incredible. Are there any open house slots available this weekend, or could we arrange a private showing?

Budget is flexible, around $4,500/month if it's worth it.

Cheers,
Nathan""",
        "805-555-0199", 4500,
        ts(days_ago=5, hour=11, minute=2),
    ))
    lead_b_id = cur.lastrowid

    # Simulate agent reply + client confirmation in thread
    cur.execute("""
        INSERT INTO leads (
            gmail_message_id, gmail_thread_id, from_email, name, subject,
            body_excerpt, body_full, phone,
            first_seen_at, is_handled
        ) VALUES (?,?,?,?,?,?,?,?,?,1)
    """, (
        f"msg_b3_{rand_id()}", thread_b,
        "trudeau.nathan@gmail.com", "Nathan T. (test)",
        "Re: Question about 1405 Cliff Dr",
        "Perfect, Sunday at 2pm works great. See you then!",
        """Perfect, Sunday at 2pm works great. See you then!

Looking forward to it.

— Nathan""",
        "805-555-0199",
        ts(days_ago=3, hour=16, minute=20),
    ))

    next_sunday = now + datetime.timedelta(days=(6 - now.weekday() + 7) % 7 + 1)
    next_sunday = next_sunday.replace(hour=14, minute=0, second=0, microsecond=0)

    cur.execute("""
        INSERT INTO appointments (
            lead_id, thread_id, status, meeting_type,
            proposed_datetime, proposed_date_text,
            proposed_address, client_name, client_email,
            context_snippet, source, detected_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        lead_b_id, thread_b, "pending", "showing",
        next_sunday.isoformat() + "Z",
        next_sunday.strftime("Sunday, %B %d at 2:00 PM"),
        "1405 Cliff Dr, Santa Barbara, CA",
        "Nathan T. (test)", "trudeau.nathan@gmail.com",
        "Perfect, Sunday at 2pm works great. See you then!",
        "inbox",
        ts(days_ago=3, hour=16, minute=30),
    ))

    print(f"  ✓ Lead B inserted (id={lead_b_id}), thread={thread_b}")
    print(f"  ✓ Appointment B inserted — status=pending, {next_sunday.strftime('%A %b %d at %I:%M %p')}")

    conn.commit()
    conn.close()

    print("\n✅ Done! Reload Lucilease dashboard to see:")
    print("   • Scenario A (violettxoxo): Pending appointment — Saturday 11am showing at 742 Anacapa")
    print("     → Hit '✅ Accept [AI]' to schedule it and send Vi a confirmation email")
    print("   • Scenario B (trudeau.nathan): Pending appointment — Sunday 2pm showing at 1405 Cliff Dr")
    print("     → Hit '✅ Accept [AI]' to schedule it")
    print("\n   Both show up in dashboard Recent Leads with ⏳ Pending status in the Appointment column.")

if __name__ == "__main__":
    main()

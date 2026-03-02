#!/usr/bin/env python3
"""
seed_march_calendar.py — Populate the appointments table with a full March 2026
calendar of fake showings. Mondays and Tuesdays are loaded with 6–8 appointments each.
Other weekdays get 1–3. Weekends get 1–2 open house slots.

All appointments are status='accepted' with fake calendar_event_ids so they
render as ✅ events on the calendar month view.

Run inside container:
  docker exec -it lucilease python /scripts/seed_march_calendar.py
"""

import sqlite3
import datetime
import random
import string
import os

DB_PATH = os.environ.get("DB_PATH", "/data/lucilease.db")

PROPERTIES = [
    ("742 Anacapa St, Santa Barbara, CA",    "showing"),
    ("1405 Cliff Dr, Santa Barbara, CA",     "showing"),
    ("88 Harbor Way, Santa Barbara, CA",     "showing"),
    ("742 Anacapa St, Santa Barbara, CA",    "open_house"),
    ("1405 Cliff Dr, Santa Barbara, CA",     "open_house"),
]

CLIENTS = [
    ("Mia Chen",        "mia.chen@example.com",       "805-555-0101"),
    ("Derek Hoffman",   "derek.h@example.com",         "805-555-0102"),
    ("Sara Okafor",     "sara.o@example.com",          "805-555-0103"),
    ("James Whitfield", "james.w@example.com",         "805-555-0104"),
    ("Lily Torres",     "lily.t@example.com",          "805-555-0105"),
    ("Ryan Patel",      "ryan.p@example.com",          "805-555-0106"),
    ("Chloe Nguyen",    "chloe.n@example.com",         "805-555-0107"),
    ("Marcus Bell",     "marcus.b@example.com",        "805-555-0108"),
    ("Aisha Grant",     "aisha.g@example.com",         "805-555-0109"),
    ("Tom Callahan",    "tom.c@example.com",           "805-555-0110"),
    ("Priya Singh",     "priya.s@example.com",         "805-555-0111"),
    ("David Kim",       "david.k@example.com",         "805-555-0112"),
    ("Fiona Reyes",     "fiona.r@example.com",         "805-555-0113"),
    ("Caleb Moore",     "caleb.m@example.com",         "805-555-0114"),
    ("Sophie Hall",     "sophie.h@example.com",        "805-555-0115"),
    ("Josh Martinez",   "josh.m@example.com",          "805-555-0116"),
    ("Emma Watson",     "emma.w@example.com",          "805-555-0117"),
    ("Liam Brooks",     "liam.b@example.com",          "805-555-0118"),
    ("Nadia Ali",       "nadia.a@example.com",         "805-555-0119"),
    ("Connor Walsh",    "connor.w@example.com",        "805-555-0120"),
]

SNIPPETS = [
    "Confirmed — see you then!",
    "Perfect, looking forward to it.",
    "Works great for us, thanks!",
    "We'll be there. Can't wait to see the place.",
    "Confirmed! We're excited.",
    "Sounds good, see you Saturday!",
    "That time works perfectly.",
    "Great, we'll bring our questions.",
    "Looking forward to the tour!",
    "Perfect timing, see you soon.",
]

def rand_id(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def rand_fp():
    return f"seed_cal_{rand_id(16)}"

def insert_lead(cur, from_email, name, phone, subject, body, first_seen_at):
    fp = rand_fp()
    cur.execute("""
        INSERT OR IGNORE INTO leads (
            fingerprint, from_email, name, phone, subject,
            body_excerpt, status, first_seen_at
        ) VALUES (?,?,?,?,?,?,?,?)
    """, (fp, from_email, name, phone, subject,
          body[:200], "handled", first_seen_at))
    return cur.lastrowid

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    inserted = 0
    client_idx = 0

    # March 2026: days 1–31
    for day in range(1, 32):
        date = datetime.date(2026, 3, day)
        weekday = date.weekday()  # 0=Mon, 6=Sun

        # Determine appointment count for the day
        if weekday in (0, 1):     # Mon, Tue — packed
            count = random.randint(6, 8)
            start_hour = 9
        elif weekday in (2, 3, 4): # Wed–Fri — moderate
            count = random.randint(1, 3)
            start_hour = 10
        elif weekday == 5:          # Saturday — open houses + 1–2 showings
            count = random.randint(1, 2)
            start_hour = 10
        else:                       # Sunday — light
            count = random.randint(0, 1)
            start_hour = 11

        if count == 0:
            continue

        # Spread appointments through the day (30-min gaps min)
        hour = start_hour
        minute = 0
        for _ in range(count):
            client = CLIENTS[client_idx % len(CLIENTS)]
            client_idx += 1
            prop, mtype = random.choice(PROPERTIES)
            c_name, c_email, c_phone = client

            appt_dt = datetime.datetime(2026, 3, day, hour, minute, 0)
            appt_iso = appt_dt.isoformat() + "Z"
            date_text = appt_dt.strftime("%A, %B %d at %-I:%M %p")

            # Fake lead
            lead_id = insert_lead(
                cur,
                from_email=c_email,
                name=c_name,
                phone=c_phone,
                subject=f"Showing request — {prop.split(',')[0]}",
                body=f"Hi, I'd like to schedule a showing for {prop}.",
                first_seen_at=(appt_dt - datetime.timedelta(days=random.randint(2, 7))).isoformat() + "Z",
            )

            cur.execute("""
                INSERT INTO appointments (
                    lead_id, thread_id, status, meeting_type,
                    proposed_datetime, proposed_date_text,
                    proposed_address, client_name, client_email,
                    context_snippet, calendar_event_id, source, detected_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                lead_id,
                f"thread_mar_{rand_id()}",
                "accepted",
                mtype,
                appt_iso,
                date_text,
                prop,
                c_name,
                c_email,
                random.choice(SNIPPETS),
                f"gcal_event_{rand_id()}",   # fake Google Calendar event id
                "inbox",
                (appt_dt - datetime.timedelta(days=random.randint(1, 5))).isoformat() + "Z",
            ))
            inserted += 1

            # Advance time slot: 45min–90min gaps on busy days, 60min otherwise
            gap = random.randint(45, 90) if weekday in (0, 1) else 60
            appt_dt += datetime.timedelta(minutes=gap)
            hour = appt_dt.hour
            minute = appt_dt.minute
            if hour >= 19:  # don't go past 7pm
                break

    conn.commit()
    conn.close()
    print(f"✅ Inserted {inserted} appointments across March 2026.")
    print("   Mondays/Tuesdays have 6–8 showings each.")
    print("   Open the Calendar tab and navigate to March 2026 to see the full month.")

if __name__ == "__main__":
    main()

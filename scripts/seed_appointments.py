"""
seed_appointments.py — Stress-test data for Lucilease Phase 4.

Inserts realistic appointment scenarios directly into the DB:
  - Pending appointments (confirmed threads, awaiting Accept/Reject)
  - Leads with confirmation-like body text
  - Varied meeting types: showings, calls, coffee, open houses
  - Partner/spouse mentioned in some
  - Mix of sources: inbox and sent mail

Run inside Docker:
    docker compose exec lucilease python /scripts/seed_appointments.py
"""

import sys
sys.path.insert(0, "/app")

import hashlib, re, datetime
from db import init_db, get_conn


def utc(offset_hours=0):
    t = datetime.datetime.utcnow() + datetime.timedelta(hours=offset_hours)
    return t.isoformat(timespec="seconds") + "Z"


def fp(email, phone=""):
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode()
    return hashlib.sha256(raw).hexdigest()


def future(days=3, hour=10):
    t = datetime.datetime.now() + datetime.timedelta(days=days)
    return t.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


# ── Leads with confirmation-like bodies (will trigger detection on next poll) ─

CONFIRMATION_LEADS = [
    {
        "from_email": "marcus.webb@gmail.com",
        "name":       "Marcus Webb",
        "phone":      "(805) 412-7731",
        "subject":    "Re: Showing at 742 Anacapa — Confirmed",
        "body_full": (
            "Hi,\n\n"
            "Perfect — Saturday at 11am works great for me. See you then at 742 Anacapa St.\n\n"
            "I'll bring my girlfriend along as well. Really looking forward to it!\n\n"
            "Thanks,\nMarcus"
        ),
        "thread_id": "thread_marcus_001",
    },
    {
        "from_email": "priya.sharma.sb@gmail.com",
        "name":       "Priya Sharma",
        "phone":      "(805) 559-0284",
        "subject":    "Re: Cliff Drive Showing — We're All Set",
        "body_full": (
            "Hello,\n\n"
            "That time works perfectly for both of us. We'll be there Thursday at 2pm "
            "at 1405 Cliff Dr. My husband Raj will be joining me.\n\n"
            "Looking forward to seeing it in person!\nPriya"
        ),
        "thread_id": "thread_priya_001",
    },
    {
        "from_email": "tyler.brooks.re@gmail.com",
        "name":       "Tyler Brooks",
        "phone":      "(805) 301-9944",
        "subject":    "Re: Quick call Tuesday — sounds good",
        "body_full": (
            "Hey,\n\n"
            "Tuesday at 3pm works perfectly for a quick call. I'll be by my phone. "
            "Looking forward to discussing the Harbor Way unit further.\n\nTyler"
        ),
        "thread_id": "thread_tyler_001",
    },
    {
        "from_email": "danielle.frost.ca@gmail.com",
        "name":       "Danielle Frost",
        "phone":      "(805) 230-6618",
        "subject":    "Coffee meeting — Friday 10am confirmed",
        "body_full": (
            "Hi,\n\n"
            "Friday at 10am at Handlebar Coffee works for me! I'll see you there. "
            "Really appreciate you making time to go over the listings.\n\nDanielle"
        ),
        "thread_id": "thread_danielle_001",
    },
    {
        "from_email": "aisha.thompson.re@gmail.com",
        "name":       "Aisha Thompson",
        "phone":      "(805) 334-9120",
        "subject":    "Open house Saturday — we're confirmed",
        "body_full": (
            "Hi there,\n\n"
            "We're confirmed for the open house this Saturday 12pm–3pm at 742 Anacapa St. "
            "My partner David will be joining me. We're very excited — this is our top choice!\n\n"
            "See you Saturday,\nAisha"
        ),
        "thread_id": "thread_aisha_001",
    },
]


# ── Pre-seeded appointments (already detected, awaiting Accept/Reject) ─────────

APPOINTMENTS = [
    {
        "client_name":       "Marcus Webb",
        "client_email":      "marcus.webb@gmail.com",
        "partner_name":      "girlfriend",
        "meeting_type":      "showing",
        "proposed_datetime": future(days=3, hour=11),
        "proposed_date_text": f"Saturday at 11:00 AM",
        "proposed_address":  "742 Anacapa St, Santa Barbara, CA 93101",
        "context_snippet":   "Saturday at 11am works great — see you then at 742 Anacapa St",
        "source":            "inbox",
        "thread_id":         "thread_marcus_001",
    },
    {
        "client_name":       "Priya Sharma",
        "client_email":      "priya.sharma.sb@gmail.com",
        "partner_name":      "Raj",
        "meeting_type":      "showing",
        "proposed_datetime": future(days=5, hour=14),
        "proposed_date_text": "Thursday at 2:00 PM",
        "proposed_address":  "1405 Cliff Dr, Santa Barbara, CA 93109",
        "context_snippet":   "We'll be there Thursday at 2pm at 1405 Cliff Dr",
        "source":            "inbox",
        "thread_id":         "thread_priya_001",
    },
    {
        "client_name":       "Tyler Brooks",
        "client_email":      "tyler.brooks.re@gmail.com",
        "partner_name":      None,
        "meeting_type":      "call",
        "proposed_datetime": future(days=2, hour=15),
        "proposed_date_text": "Tuesday at 3:00 PM",
        "proposed_address":  None,
        "context_snippet":   "Tuesday at 3pm works perfectly for a quick call",
        "source":            "inbox",
        "thread_id":         "thread_tyler_001",
    },
    {
        "client_name":       "Danielle Frost",
        "client_email":      "danielle.frost.ca@gmail.com",
        "partner_name":      None,
        "meeting_type":      "coffee",
        "proposed_datetime": future(days=4, hour=10),
        "proposed_date_text": "Friday at 10:00 AM",
        "proposed_address":  "Handlebar Coffee, Santa Barbara, CA",
        "context_snippet":   "Friday at 10am at Handlebar Coffee — I'll see you there",
        "source":            "inbox",
        "thread_id":         "thread_danielle_001",
    },
    {
        "client_name":       "Aisha Thompson",
        "client_email":      "aisha.thompson.re@gmail.com",
        "partner_name":      "David",
        "meeting_type":      "open_house",
        "proposed_datetime": future(days=6, hour=12),
        "proposed_date_text": "Saturday 12:00 PM – 3:00 PM",
        "proposed_address":  "742 Anacapa St, Santa Barbara, CA 93101",
        "context_snippet":   "Confirmed for the open house Saturday 12pm–3pm at 742 Anacapa St",
        "source":            "inbox",
        "thread_id":         "thread_aisha_001",
    },
    # One from sent mail (agent confirmed outbound)
    {
        "client_name":       "James Kowalski",
        "client_email":      "jkowalski.sb@outlook.com",
        "partner_name":      None,
        "meeting_type":      "showing",
        "proposed_datetime": future(days=7, hour=16),
        "proposed_date_text": "Next Monday at 4:00 PM",
        "proposed_address":  "1405 Cliff Dr, Santa Barbara, CA 93109",
        "context_snippet":   "Confirmed — see you Monday at 4pm at Cliff Drive",
        "source":            "sent",
        "thread_id":         "thread_kowalski_001",
    },
]


# ── Additional plain inquiry leads (no confirmation) ──────────────────────────

INQUIRY_LEADS = [
    {
        "from_email": "jkowalski.sb@outlook.com",
        "name":       "James Kowalski",
        "phone":      "(805) 884-5503",
        "subject":    "Re: 1405 Cliff Drive — Are you free Monday?",
        "body_full": (
            "Hi,\n\nWould Monday afternoon at 4pm work for a showing? "
            "My wife and I are both available then.\n\nBest, James"
        ),
        "thread_id": "thread_kowalski_001",
        "budget": 4800,
    },
    {
        "from_email": "sofia.reyes.home@gmail.com",
        "name":       "Sofia Reyes",
        "phone":      "(805) 776-2210",
        "subject":    "Anacapa St — Quick question about parking",
        "body_full": (
            "Hi,\n\nI'm very interested in the Anacapa unit. Just wanted to ask — "
            "is there dedicated parking? I work night shifts and rely on my car.\n\n"
            "Also, what's the earliest move-in date?\n\nThanks, Sofia"
        ),
        "thread_id": "thread_sofia_001",
        "budget": 3200,
    },
    {
        "from_email": "ryan.obrien.sb@gmail.com",
        "name":       "Ryan O'Brien",
        "phone":      "(805) 512-8874",
        "subject":    "Harbor Way — Flexibility on rent?",
        "body_full": (
            "Hey,\n\nLove the Harbor Way unit. Any flexibility on the price? "
            "I could do $2,300 and sign a 2-year lease upfront if that helps.\n\n"
            "Let me know, cheers — Ryan"
        ),
        "thread_id": "thread_ryan_001",
        "budget": 2300,
    },
]


def run():
    init_db()
    conn = get_conn()
    now  = utc()

    # ── Leads: confirmation emails ────────────────────────────────────────
    lead_ids = {}
    for l in CONFIRMATION_LEADS + [
        {**i, "subject": i["subject"], "from_email": i["from_email"],
         "name": i["name"], "phone": i.get("phone",""), "body_full": i["body_full"],
         "thread_id": i.get("thread_id"), "budget": i.get("budget")}
        for i in INQUIRY_LEADS
    ]:
        fingerprint_val = fp(l["from_email"], l.get("phone", ""))
        existing = conn.execute(
            "SELECT id FROM leads WHERE fingerprint=?", (fingerprint_val,)
        ).fetchone()
        if existing:
            lead_ids[l["from_email"]] = existing["id"]
            print(f"[seed] Lead exists: {l['from_email']} (id={existing['id']})")
            # Update body_full and thread_id if missing
            conn.execute("""
                UPDATE leads SET body_full=?, gmail_thread_id=?, body_excerpt=?
                WHERE id=? AND (body_full IS NULL OR body_full='')
            """, (l["body_full"], l.get("thread_id"), l["body_full"][:600], existing["id"]))
            conn.commit()
            continue

        cur = conn.execute("""
            INSERT INTO leads
                (fingerprint, source, from_email, name, phone, subject,
                 body_excerpt, body_full, budget_monthly_usd, status,
                 first_seen_at, gmail_thread_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            fingerprint_val, "fixture",
            l["from_email"], l["name"], l.get("phone",""),
            l["subject"], l["body_full"][:600], l["body_full"],
            l.get("budget_monthly_usd") or l.get("budget"),
            "new", now, l.get("thread_id"),
        ))
        lead_ids[l["from_email"]] = cur.lastrowid
        conn.commit()
        print(f"[seed] Lead inserted: {l['name']} <{l['from_email']}>")

    # ── Appointments ──────────────────────────────────────────────────────
    appt_count = 0
    for a in APPOINTMENTS:
        existing = conn.execute(
            "SELECT id FROM appointments WHERE thread_id=? AND status != 'deleted'",
            (a["thread_id"],)
        ).fetchone()
        if existing:
            print(f"[seed] Appointment exists for thread {a['thread_id']}, skipping.")
            continue

        lead_id = lead_ids.get(a["client_email"])
        conn.execute("""
            INSERT INTO appointments
                (lead_id, thread_id, detected_at, status, meeting_type,
                 proposed_datetime, proposed_date_text, proposed_address,
                 client_name, client_email, partner_name, context_snippet,
                 source, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            lead_id, a["thread_id"], now, "pending",
            a["meeting_type"], a["proposed_datetime"], a["proposed_date_text"],
            a["proposed_address"], a["client_name"], a["client_email"],
            a["partner_name"], a["context_snippet"],
            a["source"], now, now,
        ))
        conn.commit()
        appt_count += 1
        print(f"[seed] Appointment seeded: {a['meeting_type']} with {a['client_name']} — {a['proposed_date_text']}")

    conn.close()
    print(f"\n[seed] Done — {appt_count} appointments seeded.")
    print("[seed] Open http://localhost:8080 → Dashboard to see Pending Appointments.")


if __name__ == "__main__":
    run()

#!/usr/bin/env python3
"""
seed_stress_test.py — Reset + fresh inquiry seed for stress testing.

Wipes:  leads, appointments, drafts
Keeps:  clients, properties, config, open_house_slots

Seeds two raw inquiry emails (no pre-attached appointments) as if they
just arrived in the Gmail inbox. The poll loop / AI pipeline will classify
them naturally when you hit "Refresh Gmail" or "Auto-Draft All [AI]".

Properties targeted:
  - Violet  → 742 Anacapa St   (open house + general availability)
  - Nathan  → 1405 Cliff Dr    (open house + general availability)

Run:
  docker exec -it lucilease python /scripts/seed_stress_test.py
"""

import sqlite3
import datetime
import random
import string
import os

DB_PATH = os.environ.get("DB_PATH", "/data/lucilease.db")

def rand_id(n=12):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def ts_ago(days=0, hours=0):
    t = datetime.datetime.utcnow() - datetime.timedelta(days=days, hours=hours)
    return t.replace(second=0, microsecond=0).isoformat() + "Z"

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── Wipe transient tables, preserve config/clients/properties ───────────
    cur.execute("DELETE FROM leads")
    cur.execute("DELETE FROM appointments")
    cur.execute("DELETE FROM drafts")
    print("🗑  Cleared: leads, appointments, drafts")
    print("✅  Kept:    clients, properties, config, open_house_slots\n")

    # ── Helper ──────────────────────────────────────────────────────────────
    def insert_lead(from_email, name, subject, body, phone=None, budget=None,
                    days_ago=0, hours_ago=0):
        fp   = f"stress_{rand_id(16)}"
        tid  = f"thread_{rand_id(14)}"
        mid  = f"msg_{rand_id(12)}"
        ts   = ts_ago(days=days_ago, hours=hours_ago)
        cur.execute("""
            INSERT INTO leads
              (fingerprint, gmail_msg_id, gmail_thread_id,
               from_email, name, subject,
               body_excerpt, body_full,
               phone, budget_monthly_usd,
               status, first_seen_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (fp, mid, tid,
              from_email, name, subject,
              body[:300], body,
              phone, budget,
              "new", ts))
        lead_id = cur.lastrowid
        print(f"  📬 Lead #{lead_id} — {name} <{from_email}>")
        print(f"     Subject : {subject}")
        print(f"     Thread  : {tid}")
        print(f"     Received: {ts}\n")
        return lead_id, tid

    # ── Lead 1: Violet → 742 Anacapa St ─────────────────────────────────────
    print("── Lead 1: violettxoxo0@gmail.com → 742 Anacapa St ───────────────")
    insert_lead(
        from_email = "violettxoxo0@gmail.com",
        name       = "Violet",
        subject    = "Open house / showing — 742 Anacapa St?",
        body       = """\
Hi there,

I came across the listing for 742 Anacapa St and I'm really excited about it — \
the location and layout look perfect for me and my partner.

A couple of questions:
- Do you have any open house events scheduled for this property?
- If not, when would be a good time for a private showing?

I'm generally free weekday evenings after 5pm and anytime on weekends. \
Budget is around $3,200/month and we're looking to move in within 4–6 weeks.

Would love to see it as soon as possible!

Thanks,
Violet""",
        phone      = "805-555-0142",
        budget     = 3200,
        hours_ago  = 2,
    )

    # ── Lead 2: Nathan → 1405 Cliff Dr ──────────────────────────────────────
    print("── Lead 2: nathan.trudeau@gmail.com → 1405 Cliff Dr ─────────────")
    insert_lead(
        from_email = "nathan.trudeau@gmail.com",
        name       = "Nathan",
        subject    = "Interested in 1405 Cliff Dr — open house or showing?",
        body       = """\
Hello,

I spotted 1405 Cliff Dr on your site and it immediately caught my eye — \
the views from Cliff Drive are hard to beat and the floor plan looks spacious.

I have a few questions:
- Are there any upcoming open houses for this property?
- If I wanted to schedule a private tour, what does availability look like?

I'm pretty flexible — mornings work best for me, but I can also do \
Saturday afternoons. My budget is up to $4,200/month and I'm ready to move quickly \
if it's the right fit.

Let me know what works — looking forward to hearing from you!

Nathan""",
        phone      = "805-555-0199",
        budget     = 4200,
        hours_ago  = 1,
    )

    conn.commit()
    conn.close()

    print("─" * 60)
    print("✅  Seed complete!\n")
    print("Next steps:")
    print("  1. Rebuild the container:  docker compose up --build -d")
    print("  2. Open the app at        http://localhost:8080")
    print("  3. Go to Dashboard → click ↻ Refresh Gmail")
    print("     (or wait for the next poll cycle)")
    print()
    print("  The two leads should appear in Inbox as 'New'.")
    print("  Use ⚡ Auto-Draft All [AI] to generate replies.")
    print("  Reply from your Gmail to each to build threads.")
    print("  The pipeline will detect confirmations / inquiries automatically.")
    print()
    print("  Leads seeded:")
    print("    📬 violettxoxo0@gmail.com  → 742 Anacapa St   (open house / availability)")
    print("    📬 nathan.trudeau@gmail.com → 1405 Cliff Dr   (open house / availability)")

if __name__ == "__main__":
    main()

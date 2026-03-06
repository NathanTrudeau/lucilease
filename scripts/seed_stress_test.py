#!/usr/bin/env python3
"""
seed_stress_test.py — Reset leads/appts/drafts, seed 3 fresh inquiry emails.

Wipes:  leads, appointments, drafts
Keeps:  clients, properties, config, open_house_slots

Reads existing properties from DB. If none found, seeds 3 Santa Barbara ones.

Scenarios:
  1. trudeau.nathan@gmail.com  → "Porsche" (+ partner Zephyr) → inquires about Property 1
  2. nathan.trudeau@gmail.com  → "DynamiteDug" (+ partner Marigold) → inquires about Property 2
  3. trudeau.nathan@gmail.com  → "Porsche" → inquires about a FAKE property not in listings
     (tests how AI handles a property it doesn't represent)

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

def ts_ago(hours=0, minutes=0):
    t = datetime.datetime.utcnow() - datetime.timedelta(hours=hours, minutes=minutes)
    return t.replace(second=0, microsecond=0).isoformat() + "Z"

SEED_PROPERTIES = [
    {
        "address": "742 Anacapa St, Santa Barbara, CA 93101",
        "type": "rental", "bedrooms": 2, "bathrooms": 1,
        "price_monthly": 3200, "price_sale": None, "status": "active",
        "notes": "Updated kitchen, hardwood floors, street parking. Walking distance to State St.",
    },
    {
        "address": "1405 Cliff Dr, Santa Barbara, CA 93109",
        "type": "rental", "bedrooms": 3, "bathrooms": 2,
        "price_monthly": 4200, "price_sale": None, "status": "active",
        "notes": "Ocean views, large deck, private yard. Quiet neighborhood near Shoreline Park.",
    },
    {
        "address": "88 Harbor Way, Santa Barbara, CA 93109",
        "type": "rental", "bedrooms": 1, "bathrooms": 1,
        "price_monthly": 2800, "price_sale": None, "status": "active",
        "notes": "Studio/1BR loft above harbor. Exposed beams, skylight, steps from the marina.",
    },
]

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── Wipe transient tables ────────────────────────────────────────────────
    cur.execute("DELETE FROM leads")
    cur.execute("DELETE FROM appointments")
    cur.execute("DELETE FROM drafts")
    print("🗑  Cleared: leads, appointments, drafts")
    print("✅  Kept:    clients, properties, config, open_house_slots\n")

    # ── Load or seed properties ──────────────────────────────────────────────
    props = [dict(r) for r in cur.execute(
        "SELECT * FROM properties WHERE status='active' ORDER BY id LIMIT 5"
    ).fetchall()]

    if not props:
        print("📋 No active properties found — seeding 3 Santa Barbara properties...")
        now = datetime.datetime.utcnow().isoformat() + "Z"
        for p in SEED_PROPERTIES:
            cur.execute("""
                INSERT INTO properties
                  (address, type, bedrooms, bathrooms, price_monthly, price_sale, status, notes, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (p["address"], p["type"], p["bedrooms"], p["bathrooms"],
                  p["price_monthly"], p["price_sale"], p["status"], p["notes"], now, now))
        conn.commit()
        props = [dict(r) for r in cur.execute(
            "SELECT * FROM properties WHERE status='active' ORDER BY id LIMIT 5"
        ).fetchall()]
        print(f"   ✓ Seeded {len(props)} properties\n")
    else:
        print(f"📋 Found {len(props)} active properties:\n")
        for p in props:
            print(f"   • {p['address']}")
        print()

    prop1 = props[0]
    prop2 = props[1] if len(props) > 1 else props[0]
    fake_address = "999 Phantom Blvd, Santa Barbara, CA 93101"  # not in DB

    # ── Helper ──────────────────────────────────────────────────────────────
    def insert_lead(from_email, name, subject, body, phone=None, budget=None, hours_ago=0, minutes_ago=0):
        fp  = f"stress_{rand_id(16)}"
        tid = f"thread_{rand_id(14)}"
        mid = f"msg_{rand_id(12)}"
        ts  = ts_ago(hours=hours_ago, minutes=minutes_ago)
        cur.execute("""
            INSERT INTO leads
              (fingerprint, gmail_msg_id, gmail_thread_id,
               from_email, name, subject,
               body_excerpt, body_full,
               phone, budget_monthly_usd,
               status, first_seen_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (fp, mid, tid, from_email, name, subject,
              body[:300], body, phone, budget, "new", ts))
        lead_id = cur.lastrowid
        print(f"  📬 Lead #{lead_id} — {name} <{from_email}>")
        print(f"     Subject : {subject}")
        print(f"     Thread  : {tid}\n")
        return lead_id, tid

    # ── Lead 1: Porsche → Property 1 ────────────────────────────────────────
    print(f"── Lead 1: trudeau.nathan@gmail.com → {prop1['address']} ──────────")
    insert_lead(
        from_email = "trudeau.nathan@gmail.com",
        name       = "Porsche",
        subject    = f"Open house / showing — {prop1['address'].split(',')[0]}?",
        body       = f"""\
Hi there,

My name is Porsche and I came across your listing for {prop1['address']} — \
it looks absolutely stunning and my partner Zephyr and I are very excited about it.

A couple of questions:
- Do you have any open houses scheduled?
- If not, when could we arrange a private showing?

We're flexible on timing — weekday evenings and weekends work best for us. \
Budget is around ${prop1.get('price_monthly', 3500):,}/month and we're ready to move quickly \
if it's the right fit.

Looking forward to hearing from you!

Porsche""",
        phone      = "805-555-0191",
        budget     = prop1.get("price_monthly", 3500),
        hours_ago  = 3,
    )

    # ── Lead 2: DynamiteDug → Property 2 ────────────────────────────────────
    print(f"── Lead 2: nathan.trudeau@gmail.com → {prop2['address']} ──────────")
    insert_lead(
        from_email = "nathan.trudeau@gmail.com",
        name       = "DynamiteDug",
        subject    = f"Interested in {prop2['address'].split(',')[0]} — open house or tour?",
        body       = f"""\
Hello,

I'm DynamiteDug — found your listing for {prop2['address']} and it's exactly \
what my partner Marigold and I have been looking for.

Questions:
- Any upcoming open houses for this property?
- What does your availability look like for private tours?

Mornings work best for me, but I can also do Saturday afternoons. \
We're looking at a budget of ${prop2.get('price_monthly', 4200):,}/month \
and are ready to move fast if the place is as good as the photos suggest.

Thanks!
DynamiteDug""",
        phone      = "805-555-0177",
        budget     = prop2.get("price_monthly", 4200),
        hours_ago  = 1,
        minutes_ago = 30,
    )

    # ── Lead 3: Porsche → FAKE property (not listed) ─────────────────────────
    print(f"── Lead 3: trudeau.nathan@gmail.com → {fake_address} (NOT LISTED) ──")
    insert_lead(
        from_email = "trudeau.nathan@gmail.com",
        name       = "Porsche",
        subject    = f"Inquiry about {fake_address.split(',')[0]}",
        body       = f"""\
Hi,

Porsche again! I also saw a reference to a listing at {fake_address} — \
is that one of your properties as well?

If so, Zephyr and I would love to take a look at that one too. \
Do you have any availability this weekend for a showing?

Thanks,
Porsche""",
        phone      = "805-555-0191",
        budget     = 3500,
        minutes_ago = 45,
    )

    conn.commit()
    conn.close()

    print("─" * 60)
    print("✅  Seed complete!\n")
    print("Test accounts:")
    print("  📬 trudeau.nathan@gmail.com  → Porsche  (partner: Zephyr)")
    print("  📬 nathan.trudeau@gmail.com  → DynamiteDug  (partner: Marigold)")
    print()
    print("Scenarios:")
    print(f"  1. Porsche      → {prop1['address'].split(',')[0]}  (valid listing)")
    print(f"  2. DynamiteDug  → {prop2['address'].split(',')[0]}  (valid listing)")
    print(f"  3. Porsche      → {fake_address.split(',')[0]}  ❌ NOT in your listings")
    print()
    print("Next steps:")
    print("  1. Open http://localhost:8080")
    print("  2. Dashboard → ↻ Refresh Gmail  (or wait for next poll)")
    print("  3. Leads appear in Inbox as 'New'")
    print("  4. ⚡ Auto-Draft All [AI]  — watch how AI handles the fake property")
    print("  5. Review drafts → send")
    print("  6. Reply from test accounts to confirm → pipeline detects appointment")

if __name__ == "__main__":
    main()

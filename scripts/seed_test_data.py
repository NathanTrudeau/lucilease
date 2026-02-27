"""
seed_test_data.py — Plant 10 realistic test leads into the Lucilease database.

Run inside Docker:
    docker compose exec lucilease python /app/scripts/seed_test_data.py

This simulates a real inbox: 3 properties, 10 prospective clients, a mix of
rental inquiries, showing requests, and budget discussions.
"""

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

import hashlib, re, json
from db import init_db, get_conn

# ── Properties ────────────────────────────────────────────────────────────────

PROPERTIES = [
    {
        "address":       "742 Anacapa St, Santa Barbara, CA 93101",
        "type":          "rental",
        "bedrooms":      2,
        "bathrooms":     1.0,
        "price_monthly": 3200,
        "notes":         "Charming downtown unit, hardwood floors, in-unit laundry, pet-friendly with deposit.",
    },
    {
        "address":       "1405 Cliff Dr, Santa Barbara, CA 93109",
        "type":          "rental",
        "bedrooms":      3,
        "bathrooms":     2.0,
        "price_monthly": 4800,
        "notes":         "Mesa area, ocean views, private backyard, 2-car garage, no smoking.",
    },
    {
        "address":       "88 Harbor Way, Santa Barbara, CA 93109",
        "type":          "rental",
        "bedrooms":      1,
        "bathrooms":     1.0,
        "price_monthly": 2400,
        "notes":         "Steps from the harbor, newly renovated kitchen, rooftop deck access.",
    },
]

# ── Test leads ────────────────────────────────────────────────────────────────
# 5 inquiries → trudeau.nathan@gmail.com
# 5 inquiries → violettxoxo@gmail.com

LEADS = [
    # ── Trudeau inbox ─────────────────────────────────────────────────────────
    {
        "from_email": "marcus.webb@gmail.com",
        "name":       "Marcus Webb",
        "phone":      "(805) 412-7731",
        "subject":    "Inquiry — 742 Anacapa St",
        "body_excerpt": (
            "Hi, I came across your listing for the 2-bedroom at 742 Anacapa St and I'm very "
            "interested. I'm looking to move in around March 1st. Budget is around $3,200/month. "
            "I have a small dog (under 20lbs) — is that okay? Would love to schedule a showing "
            "this weekend if possible. Best, Marcus"
        ),
        "budget_monthly_usd": 3200,
        "inbox": "trudeau.nathan@gmail.com",
    },
    {
        "from_email": "priya.sharma.sb@gmail.com",
        "name":       "Priya Sharma",
        "phone":      "(805) 559-0284",
        "subject":    "Cliff Drive 3BR — Available?",
        "body_excerpt": (
            "Hello, I saw the 3-bedroom on Cliff Dr and it looks perfect for my family. "
            "We're relocating from San Jose in early April. Our budget is $4,500–$5,000/month. "
            "Could you let me know if it'll be available April 1st? We have two kids and no pets. "
            "Happy to do a video tour first. Thanks, Priya"
        ),
        "budget_monthly_usd": 4800,
        "inbox": "trudeau.nathan@gmail.com",
    },
    {
        "from_email": "tyler.brooks.re@gmail.com",
        "name":       "Tyler Brooks",
        "phone":      "(805) 301-9944",
        "subject":    "Harbor Way Unit — Showing Request",
        "body_excerpt": (
            "Hey there! The 1-bedroom at 88 Harbor Way caught my eye — the rooftop deck is a "
            "huge plus. I work remotely and love being near the water. Budget is $2,400/mo. "
            "Can we set up a showing next week? Anytime Tuesday or Wednesday works for me. "
            "— Tyler"
        ),
        "budget_monthly_usd": 2400,
        "inbox": "trudeau.nathan@gmail.com",
    },
    {
        "from_email": "sofia.reyes.home@gmail.com",
        "name":       "Sofia Reyes",
        "phone":      "(805) 776-2210",
        "subject":    "Anacapa St Rental Inquiry",
        "body_excerpt": (
            "Hi! I'm a nurse at Cottage Hospital and looking for a place close to downtown. "
            "The Anacapa St unit looks great. My budget is $3,000–$3,400/month. "
            "Move-in would be February 15th ideally. Is parking included? "
            "Looking forward to hearing from you. Sofia Reyes"
        ),
        "budget_monthly_usd": 3200,
        "inbox": "trudeau.nathan@gmail.com",
    },
    {
        "from_email": "jkowalski.sb@outlook.com",
        "name":       "James Kowalski",
        "phone":      "(805) 884-5503",
        "subject":    "Re: 1405 Cliff Drive Rental",
        "body_excerpt": (
            "Good morning, I'm reaching out about the Cliff Drive property. We're a couple "
            "looking for a 3BR in the Mesa area. The ocean view is a big selling point for us. "
            "We're flexible on move-in — anywhere from March 15 to April 15. Budget up to $5,000. "
            "Do you allow 1-year leases? Thanks, James"
        ),
        "budget_monthly_usd": 4800,
        "inbox": "trudeau.nathan@gmail.com",
    },
    # ── Violett inbox ─────────────────────────────────────────────────────────
    {
        "from_email": "danielle.frost.ca@gmail.com",
        "name":       "Danielle Frost",
        "phone":      "(805) 230-6618",
        "subject":    "Harbor Way — Is It Still Available?",
        "body_excerpt": (
            "Hi there! A friend recommended your listings. I'm looking at the Harbor Way "
            "1BR — it's exactly what I've been searching for. $2,400/mo works for me. "
            "I'm currently month-to-month so I can move fast. Can we do a showing this week? "
            "Thanks so much, Danielle"
        ),
        "budget_monthly_usd": 2400,
        "inbox": "violettxoxo@gmail.com",
    },
    {
        "from_email": "ethan.nguyen.renter@gmail.com",
        "name":       "Ethan Nguyen",
        "phone":      "(805) 441-7892",
        "subject":    "742 Anacapa — Application Question",
        "body_excerpt": (
            "Hello, I toured a similar unit in your building last year and loved it. "
            "I'm a UCSB grad student now working full-time at a tech startup in Goleta. "
            "Budget is $3,200/month. I'd love to start an application for Anacapa St "
            "if there's any availability. Is there a waitlist? — Ethan"
        ),
        "budget_monthly_usd": 3200,
        "inbox": "violettxoxo@gmail.com",
    },
    {
        "from_email": "c.martinez.design@gmail.com",
        "name":       "Chloe Martinez",
        "phone":      "(805) 667-3301",
        "subject":    "Cliff Dr 3BR — Family Rental",
        "body_excerpt": (
            "Hi! My husband and I are looking for a 3-bedroom with a yard for our two dogs. "
            "The Cliff Dr listing looks beautiful — ocean views would be amazing. "
            "We're both remote workers, very quiet tenants. Budget around $4,800–$5,000. "
            "Target move-in is May 1st. Please let me know next steps! Chloe"
        ),
        "budget_monthly_usd": 4800,
        "inbox": "violettxoxo@gmail.com",
    },
    {
        "from_email": "ryan.obrien.sb@gmail.com",
        "name":       "Ryan O'Brien",
        "phone":      "(805) 512-8874",
        "subject":    "Harbor Way Showing — Next Week?",
        "body_excerpt": (
            "Hey, saw the Harbor Way 1BR on your site. The renovated kitchen and rooftop are "
            "exactly what I want. I'm a chef at a downtown restaurant so being close to the harbor "
            "is a dream. Budget is $2,300–$2,500/mo. Available for a showing Mon–Wed next week. "
            "Cheers, Ryan"
        ),
        "budget_monthly_usd": 2400,
        "inbox": "violettxoxo@gmail.com",
    },
    {
        "from_email": "aisha.thompson.re@gmail.com",
        "name":       "Aisha Thompson",
        "phone":      "(805) 334-9120",
        "subject":    "Interested in 742 Anacapa St",
        "body_excerpt": (
            "Hello! I'm moving to Santa Barbara for a new position at the county. "
            "The Anacapa St 2BR looks perfect — downtown access is important for my commute. "
            "I have excellent rental history and references available. Budget: $3,000–$3,400/mo. "
            "Move-in: March 1st. Can we schedule a showing? Best, Aisha Thompson"
        ),
        "budget_monthly_usd": 3200,
        "inbox": "violettxoxo@gmail.com",
    },
]


def fingerprint(email, phone=""):
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode()
    return hashlib.sha256(raw).hexdigest()


def utc():
    import datetime
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def run():
    init_db()
    conn = get_conn()

    # ── Upsert properties ──────────────────────────────────────────────────
    prop_count = 0
    for p in PROPERTIES:
        exists = conn.execute(
            "SELECT id FROM properties WHERE address=?", (p["address"],)
        ).fetchone()
        if not exists:
            conn.execute("""
                INSERT INTO properties
                    (address, type, bedrooms, bathrooms, price_monthly, status, notes, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (p["address"], p["type"], p["bedrooms"], p["bathrooms"],
                  p["price_monthly"], "active", p["notes"], utc(), utc()))
            prop_count += 1

    conn.commit()
    print(f"[seed] {prop_count} properties added ({len(PROPERTIES) - prop_count} already existed).")

    # ── Insert leads ───────────────────────────────────────────────────────
    lead_count = 0
    skip_count = 0
    for l in LEADS:
        fp = fingerprint(l["from_email"], l["phone"])
        exists = conn.execute(
            "SELECT id FROM leads WHERE fingerprint=?", (fp,)
        ).fetchone()
        if exists:
            skip_count += 1
            continue

        conn.execute("""
            INSERT INTO leads
                (fingerprint, source, from_email, name, phone, subject,
                 body_excerpt, budget_monthly_usd, status, first_seen_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (fp, "fixture", l["from_email"], l["name"], l["phone"],
              l["subject"], l["body_excerpt"], l["budget_monthly_usd"],
              "new", utc()))
        lead_count += 1

    conn.commit()
    conn.close()

    print(f"[seed] {lead_count} leads added ({skip_count} duplicates skipped).")
    print(f"[seed] Done. Open http://localhost:8080 → Inbox to see your test leads.")


if __name__ == "__main__":
    run()

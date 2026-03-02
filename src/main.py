"""
main.py — Lucilease FastAPI application.
"""

import asyncio
import datetime
import os
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from db import init_db, get_conn
import gmail as gm

STATIC    = pathlib.Path(__file__).parent / "static"
POLL_SECS = int(os.getenv("POLL_SECONDS", "300"))


# ── Background polling ────────────────────────────────────────────────────────

async def _poll_loop():
    while True:
        await asyncio.sleep(POLL_SECS)
        try:
            found = await asyncio.to_thread(gm.poll_inbox)
            if found:
                print(f"[poll] {found} new lead(s) stored.")
        except Exception as e:
            print(f"[poll] Error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print(f"[lucilease] Started — http://localhost:8080  (poll every {POLL_SECS}s)")
    task = asyncio.create_task(_poll_loop())
    yield
    task.cancel()


app = FastAPI(title="Lucilease", version="0.3.0", lifespan=lifespan)


# ── Health ────────────────────────────────────────────────────────────────────

APP_VERSION = "0.4.1"

@app.get("/health")
async def health():
    return {
        "status":        "ok",
        "version":       APP_VERSION,
        "authenticated": gm.is_authenticated(),
        "poll_seconds":  POLL_SECS,
        "timestamp":     datetime.datetime.utcnow().isoformat() + "Z",
    }


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.get("/auth/gmail")
async def auth_gmail():
    return RedirectResponse(gm.get_auth_url())


@app.get("/auth/callback")
async def auth_callback(
    code: str = None,
    error: str = None,
    error_description: str = None,
    state: str = None,
    scope: str = None,
):
    if error:
        msg = error_description or error
        print(f"[auth] OAuth error from Google: {msg}")
        return RedirectResponse(f"/?auth_error={msg}")
    if not code:
        print("[auth] OAuth callback received with no code and no error.")
        return RedirectResponse("/?auth_error=no_code")
    try:
        await asyncio.to_thread(gm.exchange_code, code)
    except Exception as e:
        print(f"[auth] Token exchange failed: {e}")
        return RedirectResponse(f"/?auth_error=token_exchange_failed")
    asyncio.create_task(asyncio.to_thread(gm.poll_inbox))
    return RedirectResponse("/?connected=1")


@app.get("/auth/status")
async def auth_status():
    return {"authenticated": gm.is_authenticated()}


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def stats():
    conn = get_conn()
    cur  = conn.cursor()
    leads_new   = cur.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
    leads_total = cur.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    clients     = cur.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    properties  = cur.execute("SELECT COUNT(*) FROM properties").fetchone()[0]

    # Breakdowns for summary bars
    client_rows = cur.execute("SELECT status, COUNT(*) as n FROM clients GROUP BY status").fetchall()
    prop_rows   = cur.execute("SELECT status, COUNT(*) as n FROM properties GROUP BY status").fetchall()
    conn.close()

    return {
        "leads_new":    leads_new,
        "leads_total":  leads_total,
        "clients":      clients,
        "properties":   properties,
        "clients_by_status":    {r["status"]: r["n"] for r in client_rows},
        "properties_by_status": {r["status"]: r["n"] for r in prop_rows},
    }


# ── Leads ─────────────────────────────────────────────────────────────────────

@app.get("/api/leads")
async def get_leads(status: str = "new"):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM leads WHERE status=? ORDER BY first_seen_at DESC", (status,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/leads/{lead_id}/handle")
async def handle_lead(lead_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE leads SET status='handled', handled_at=? WHERE id=?",
        (datetime.datetime.utcnow().isoformat() + "Z", lead_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/leads/{lead_id}/archive")
async def archive_lead(lead_id: int):
    conn = get_conn()
    row = conn.execute("SELECT gmail_msg_id FROM leads WHERE id=?", (lead_id,)).fetchone()
    conn.execute("UPDATE leads SET status='archived' WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()
    # Mirror archive to Gmail (best-effort)
    if row and row["gmail_msg_id"]:
        creds = gm.get_credentials()
        if creds:
            await asyncio.to_thread(gm.archive_gmail_message, creds, row["gmail_msg_id"])
    return {"ok": True}


@app.post("/api/leads/{lead_id}/unarchive")
async def unarchive_lead(lead_id: int):
    conn = get_conn()
    conn.execute("UPDATE leads SET status='new' WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()
    # Note: we don't move back to Gmail inbox — user can do that in Gmail if needed
    return {"ok": True}


class BulkArchiveRequest(BaseModel):
    ids: list[int]

@app.post("/api/leads/archive-bulk")
async def archive_bulk(req: BulkArchiveRequest):
    conn = get_conn()
    msg_ids = []
    for lead_id in req.ids:
        row = conn.execute("SELECT gmail_msg_id FROM leads WHERE id=?", (lead_id,)).fetchone()
        if row and row["gmail_msg_id"]:
            msg_ids.append(row["gmail_msg_id"])
        conn.execute("UPDATE leads SET status='archived' WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()
    # Mirror all to Gmail (best-effort, parallel)
    if msg_ids:
        creds = gm.get_credentials()
        if creds:
            await asyncio.gather(*[
                asyncio.to_thread(gm.archive_gmail_message, creds, mid)
                for mid in msg_ids
            ])
    return {"ok": True, "archived": len(req.ids)}


@app.post("/api/leads/{lead_id}/add-client")
async def add_client_from_lead(lead_id: int):
    conn = get_conn()
    lead = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not lead:
        conn.close()
        return {"ok": False, "error": "Lead not found"}
    now = datetime.datetime.utcnow().isoformat() + "Z"
    try:
        conn.execute("""
            INSERT INTO clients (name, email, phone, status, created_at, updated_at)
            VALUES (?,?,?,?,?,?)
        """, (lead["name"] or lead["from_email"], lead["from_email"],
              lead["phone"], "active", now, now))
        conn.commit()
    except Exception:
        pass
    conn.close()
    return {"ok": True}


@app.post("/api/leads/{lead_id}/draft")
async def create_draft(lead_id: int):
    """Generate a Claude reply draft for a lead and push it to Gmail."""
    try:
        from ai import draft_reply
        result = await asyncio.to_thread(draft_reply, lead_id)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/poll")
async def manual_poll():
    found = await asyncio.to_thread(gm.poll_inbox)
    return {"new_leads": found}


# ── Agent profile ─────────────────────────────────────────────────────────────

class AgentProfile(BaseModel):
    agent_name:              str
    agent_company:           Optional[str] = ""
    agent_tone:              Optional[str] = "professional and warm"
    agent_signature:         Optional[str] = ""
    agent_signature_enabled: Optional[str] = "false"


@app.get("/api/profile")
async def get_profile():
    from ai import get_agent_profile
    return get_agent_profile()


@app.post("/api/profile")
async def save_profile(profile: AgentProfile):
    from ai import save_agent_profile
    save_agent_profile(profile.model_dump())
    return {"ok": True}


# ── Drafts ───────────────────────────────────────────────────────────────────

class DraftIn(BaseModel):
    to_email: str
    subject:  str
    body:     str


@app.get("/api/drafts/sent")
async def get_sent_drafts():
    """Return all sent drafts."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM drafts WHERE status='sent' ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/drafts")
async def get_drafts():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM drafts WHERE status IS NULL OR status != 'sent' ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[drafts] GET error: {e}")
        return []
    finally:
        conn.close()


@app.post("/api/drafts")
async def create_draft_manual(draft: DraftIn):
    """Create a new local draft manually (not from a lead)."""
    now = datetime.datetime.utcnow().isoformat() + "Z"
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO drafts (to_email, subject, body, status, created_at, updated_at)
        VALUES (?,?,?,?,?,?)
    """, (draft.to_email, draft.subject, draft.body, "local", now, now))
    draft_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "id": draft_id, "status": "local"}


@app.patch("/api/drafts/{draft_id}")
async def update_draft(draft_id: int, draft: DraftIn):
    """Edit a draft locally and optionally sync to Gmail if it has a draft id."""
    now = datetime.datetime.utcnow().isoformat() + "Z"
    conn = get_conn()
    row = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "error": "Draft not found"}

    row = dict(row)
    # Auto-promote duplicate → local if subject AND body are now unique
    new_status = row["status"]
    if row["status"] == "duplicate":
        new_status = _check_duplicate_status(conn, draft_id, draft.to_email, draft.body)

    conn.execute("""
        UPDATE drafts SET to_email=?, subject=?, body=?, status=?, updated_at=? WHERE id=?
    """, (draft.to_email, draft.subject, draft.body, new_status, now, draft_id))
    conn.commit()
    conn.close()

    # If synced to Gmail drafts, update there too
    if row.get("gmail_draft_id") and new_status != "duplicate":
        creds = gm.get_credentials()
        if creds:
            try:
                await asyncio.to_thread(
                    gm.update_gmail_draft, creds,
                    row["gmail_draft_id"], draft.to_email, draft.subject, draft.body
                )
            except Exception as e:
                print(f"[drafts] Gmail sync failed: {e}")

    return {"ok": True, "status": new_status}


@app.delete("/api/drafts/{draft_id}")
async def delete_draft(draft_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "error": "Not found"}
    row = dict(row)
    conn.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/drafts/{draft_id}/duplicate")
async def duplicate_draft(draft_id: int):
    """Clone a draft and mark it as a duplicate until subject+body are both changed."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "error": "Not found"}
    row = dict(row)
    now = datetime.datetime.utcnow().isoformat() + "Z"
    cur = conn.execute("""
        INSERT INTO drafts (lead_id, to_email, subject, body, status, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?)
    """, (row.get("lead_id"), row.get("to_email"),
          row.get("subject"), row.get("body"),
          "duplicate", now, now))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "id": new_id}


def _check_duplicate_status(conn, draft_id: int, to_email: str, body: str) -> str:
    """
    Return 'local' if body AND to_email are both unique among all other drafts.
    Subject may repeat — that's fine (e.g. 'Re: Property Inquiry' for many clients).
    """
    others = conn.execute(
        "SELECT to_email, body FROM drafts WHERE id != ? AND status != 'sent'",
        (draft_id,)
    ).fetchall()
    email_clean = (to_email or "").strip().lower()
    body_clean  = (body or "").strip().lower()
    for other in others:
        other_email = (other["to_email"] or "").strip().lower()
        other_body  = (other["body"] or "").strip().lower()
        if email_clean == other_email and body_clean == other_body:
            return "duplicate"
    return "local"


@app.post("/api/drafts/{draft_id}/push-gmail")
async def push_draft_to_gmail(draft_id: int):
    """Push a local draft to Gmail Drafts."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "error": "Not found"}
    row = dict(row)
    creds = gm.get_credentials()
    if not creds:
        conn.close()
        return {"ok": False, "error": "Gmail not connected"}
    try:
        gmail_id = await asyncio.to_thread(
            gm.create_gmail_draft_public, creds,
            row["to_email"], row["subject"], row["body"]
        )
        now = datetime.datetime.utcnow().isoformat() + "Z"
        conn.execute(
            "UPDATE drafts SET gmail_draft_id=?, status='gmail_draft', updated_at=? WHERE id=?",
            (gmail_id, now, draft_id)
        )
        conn.commit()
        conn.close()
        return {"ok": True, "gmail_draft_id": gmail_id}
    except Exception as e:
        conn.close()
        return {"ok": False, "error": str(e)}


@app.post("/api/drafts/{draft_id}/send")
async def send_single_draft(draft_id: int):
    """Send a single draft via Gmail."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    conn.close()
    if not row:
        return {"ok": False, "error": "Draft not found"}
    row = dict(row)

    creds = gm.get_credentials()
    if not creds:
        return {"ok": False, "error": "Gmail not connected"}

    now = datetime.datetime.utcnow().isoformat() + "Z"
    try:
        if row.get("gmail_draft_id"):
            await asyncio.to_thread(gm.send_gmail_draft, creds, row["gmail_draft_id"])
        else:
            await asyncio.to_thread(
                gm.send_gmail_message, creds,
                row["to_email"], row["subject"], row["body"]
            )
        conn2 = get_conn()
        conn2.execute(
            "UPDATE drafts SET status='sent', error_msg=NULL, updated_at=? WHERE id=?",
            (now, draft_id)
        )
        conn2.commit()
        conn2.close()
        return {"ok": True}
    except Exception as e:
        err = str(e)
        conn2 = get_conn()
        conn2.execute(
            "UPDATE drafts SET status='failed', error_msg=?, updated_at=? WHERE id=?",
            (err, now, draft_id)
        )
        conn2.commit()
        conn2.close()
        return {"ok": False, "error": err}


@app.post("/api/drafts/send-all")
async def send_all_drafts():
    """Send all pending drafts via Gmail. Returns per-draft results."""
    conn  = get_conn()
    rows  = conn.execute(
        "SELECT * FROM drafts WHERE status IN ('local','gmail_draft','failed')"
    ).fetchall()
    conn.close()

    creds = gm.get_credentials()
    if not creds:
        return {"ok": False, "error": "Gmail not connected"}

    results = []
    for row in rows:
        row = dict(row)
        now = datetime.datetime.utcnow().isoformat() + "Z"
        try:
            if row.get("gmail_draft_id"):
                await asyncio.to_thread(gm.send_gmail_draft, creds, row["gmail_draft_id"])
            else:
                await asyncio.to_thread(
                    gm.send_gmail_message, creds,
                    row["to_email"], row["subject"], row["body"]
                )
            conn2 = get_conn()
            conn2.execute(
                "UPDATE drafts SET status='sent', error_msg=NULL, updated_at=? WHERE id=?",
                (now, row["id"])
            )
            conn2.commit()
            conn2.close()
            results.append({"id": row["id"], "to": row["to_email"], "ok": True})
        except Exception as e:
            err = str(e)
            conn2 = get_conn()
            conn2.execute(
                "UPDATE drafts SET status='failed', error_msg=?, updated_at=? WHERE id=?",
                (err, now, row["id"])
            )
            conn2.commit()
            conn2.close()
            results.append({"id": row["id"], "to": row["to_email"], "ok": False, "error": err})

    sent  = sum(1 for r in results if r["ok"])
    failed = sum(1 for r in results if not r["ok"])
    return {"ok": True, "sent": sent, "failed": failed, "results": results}


# ── Gmail account info ────────────────────────────────────────────────────────

@app.get("/api/gmail-account")
async def gmail_account():
    creds = gm.get_credentials()
    if not creds:
        return {"email": None}
    try:
        from googleapiclient.discovery import build as gbuild
        service = gbuild("gmail", "v1", credentials=creds, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        return {"email": profile.get("emailAddress")}
    except Exception as e:
        return {"email": None, "error": str(e)}


@app.delete("/auth/gmail")
async def disconnect_gmail():
    """Disconnect Gmail by deleting the stored token."""
    token = gm.TOKEN_FILE
    if token.exists():
        token.unlink()
    return {"ok": True}


# ── Clients ───────────────────────────────────────────────────────────────────

@app.get("/api/clients")
async def get_clients():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM clients ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


class ClientIn(BaseModel):
    name:    str
    email:   Optional[str] = None
    phone:   Optional[str] = None
    address: Optional[str] = None
    notes:   Optional[str] = None
    status:  Optional[str] = "active"


@app.post("/api/clients")
async def create_client(client: ClientIn):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    conn = get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO clients (name, email, phone, address, notes, status, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (client.name, client.email, client.phone, client.address,
              client.notes, client.status, now, now))
        conn.commit()
        new_id = cur.lastrowid
    except Exception as e:
        conn.close()
        return {"ok": False, "error": str(e)}
    conn.close()
    return {"ok": True, "id": new_id}


@app.patch("/api/clients/{client_id}")
async def update_client(client_id: int, client: ClientIn):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    conn = get_conn()
    conn.execute("""
        UPDATE clients SET name=?, email=?, phone=?, address=?, notes=?, status=?, updated_at=?
        WHERE id=?
    """, (client.name, client.email, client.phone, client.address,
          client.notes, client.status, now, client_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/clients/{client_id}")
async def delete_client(client_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ── Properties ────────────────────────────────────────────────────────────────

@app.get("/api/properties")
async def get_properties():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM properties ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


class PropertyIn(BaseModel):
    address:       str
    type:          str = "rental"
    bedrooms:      Optional[int] = None
    bathrooms:     Optional[float] = None
    price_monthly: Optional[int] = None
    price_sale:    Optional[int] = None
    status:        Optional[str] = "active"
    notes:         Optional[str] = None


@app.post("/api/properties")
async def add_property(prop: PropertyIn):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO properties
            (address, type, bedrooms, bathrooms, price_monthly, price_sale, status, notes, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (prop.address, prop.type, prop.bedrooms, prop.bathrooms,
          prop.price_monthly, prop.price_sale, prop.status or "active", prop.notes, now, now))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"ok": True, "id": new_id}


@app.patch("/api/properties/{prop_id}")
async def update_property(prop_id: int, prop: PropertyIn):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    conn = get_conn()
    conn.execute("""
        UPDATE properties SET address=?, type=?, bedrooms=?, bathrooms=?,
            price_monthly=?, price_sale=?, status=?, notes=?, updated_at=?
        WHERE id=?
    """, (prop.address, prop.type, prop.bedrooms, prop.bathrooms,
          prop.price_monthly, prop.price_sale, prop.status or "active",
          prop.notes, now, prop_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/properties/{prop_id}")
async def delete_property(prop_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM properties WHERE id=?", (prop_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ── Open house slots ──────────────────────────────────────────────────────────

class OpenHouseSlot(BaseModel):
    day_of_week: str
    start_time:  str
    end_time:    str
    label:       Optional[str] = None

@app.get("/api/properties/{prop_id}/open-house-slots")
async def get_open_house_slots(prop_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM open_house_slots WHERE property_id=? ORDER BY day_of_week, start_time",
        (prop_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/properties/{prop_id}/open-house-slots")
async def add_open_house_slot(prop_id: int, slot: OpenHouseSlot):
    conn = get_conn()
    now = datetime.datetime.utcnow().isoformat() + "Z"
    cur = conn.execute("""
        INSERT INTO open_house_slots (property_id, day_of_week, start_time, end_time, label, created_at)
        VALUES (?,?,?,?,?,?)
    """, (prop_id, slot.day_of_week.lower(), slot.start_time, slot.end_time, slot.label, now))
    conn.commit()
    slot_id = cur.lastrowid
    conn.close()
    return {"ok": True, "id": slot_id}

@app.delete("/api/open-house-slots/{slot_id}")
async def delete_open_house_slot(slot_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM open_house_slots WHERE id=?", (slot_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ── Thread view ───────────────────────────────────────────────────────────────

@app.get("/api/leads/{lead_id}/thread")
async def get_lead_thread(lead_id: int):
    conn = get_conn()
    lead = conn.execute("SELECT gmail_thread_id FROM leads WHERE id=?", (lead_id,)).fetchone()
    conn.close()
    if not lead or not lead["gmail_thread_id"]:
        return {"ok": False, "error": "No thread ID for this lead"}
    creds = gm.get_credentials()
    if not creds:
        return {"ok": False, "error": "Gmail not connected"}
    try:
        messages = await asyncio.to_thread(gm.get_thread_messages, creds, lead["gmail_thread_id"])
        return {"ok": True, "messages": messages}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Availability windows + timezone (stored in config table) ──────────────────

class AvailabilityConfig(BaseModel):
    timezone: Optional[str] = None
    availability_windows: Optional[str] = None  # JSON string

@app.get("/api/config/availability")
async def get_availability():
    conn = get_conn()
    tz   = conn.execute("SELECT value FROM config WHERE key='timezone'").fetchone()
    avail = conn.execute("SELECT value FROM config WHERE key='availability_windows'").fetchone()
    conn.close()
    return {
        "timezone": tz["value"] if tz else "America/Los_Angeles",
        "availability_windows": avail["value"] if avail else None,
    }

@app.post("/api/config/availability")
async def save_availability(cfg: AvailabilityConfig):
    conn = get_conn()
    now = datetime.datetime.utcnow().isoformat() + "Z"
    if cfg.timezone is not None:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value, updated_at) VALUES ('timezone',?,?)",
            (cfg.timezone, now)
        )
    if cfg.availability_windows is not None:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value, updated_at) VALUES ('availability_windows',?,?)",
            (cfg.availability_windows, now)
        )
    conn.commit()
    conn.close()
    return {"ok": True}


# ── Static + SPA ──────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    return FileResponse(str(STATIC / "index.html"))

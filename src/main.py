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

APP_VERSION = "0.3.0"

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
async def auth_callback(code: str):
    await asyncio.to_thread(gm.exchange_code, code)
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
    properties  = cur.execute("SELECT COUNT(*) FROM properties WHERE status='active'").fetchone()[0]
    conn.close()
    return {
        "leads_new":   leads_new,
        "leads_total": leads_total,
        "clients":     clients,
        "properties":  properties,
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


@app.get("/api/drafts")
async def get_drafts():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM drafts WHERE status != 'sent' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
    conn.execute("""
        UPDATE drafts SET to_email=?, subject=?, body=?, updated_at=? WHERE id=?
    """, (draft.to_email, draft.subject, draft.body, now, draft_id))
    conn.commit()
    conn.close()

    # If synced to Gmail drafts, update there too
    if row.get("gmail_draft_id"):
        creds = gm.get_credentials()
        if creds:
            try:
                await asyncio.to_thread(
                    gm.update_gmail_draft, creds,
                    row["gmail_draft_id"], draft.to_email, draft.subject, draft.body
                )
            except Exception as e:
                print(f"[drafts] Gmail sync failed: {e}")

    return {"ok": True}


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
        "SELECT * FROM properties WHERE status='active' ORDER BY created_at DESC"
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
    notes:         Optional[str] = None


@app.post("/api/properties")
async def add_property(prop: PropertyIn):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    conn = get_conn()
    conn.execute("""
        INSERT INTO properties
            (address, type, bedrooms, bathrooms, price_monthly, price_sale, status, notes, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (prop.address, prop.type, prop.bedrooms, prop.bathrooms,
          prop.price_monthly, prop.price_sale, "active", prop.notes, now, now))
    conn.commit()
    conn.close()
    return {"ok": True}


# ── Static + SPA ──────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    return FileResponse(str(STATIC / "index.html"))

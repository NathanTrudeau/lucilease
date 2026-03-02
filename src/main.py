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
import calendar_service as cal

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
            # Scan for confirmations in both inbox leads and sent mail
            await asyncio.to_thread(_scan_confirmations)
        except Exception as e:
            print(f"[poll] Error: {e}")


def _scan_confirmations():
    """
    Scan recent inbox leads + sent mail for appointment confirmations.
    Runs Claude detection on qualifying threads and inserts into appointments table.
    """
    from ai import detect_confirmation
    creds = gm.get_credentials()
    if not creds:
        return

    conn = get_conn()
    now  = datetime.datetime.utcnow().isoformat() + "Z"

    # --- Incoming leads that are confirmation candidates ---
    recent_leads = conn.execute("""
        SELECT id, subject, body_full, body_excerpt, gmail_thread_id, from_email, name
        FROM leads
        WHERE status = 'new'
        AND gmail_thread_id IS NOT NULL
        AND first_seen_at > datetime('now', '-7 days')
    """).fetchall()

    for lead in recent_leads:
        lead = dict(lead)
        subject = lead.get("subject", "")
        body    = lead.get("body_full") or lead.get("body_excerpt") or ""

        if not gm.is_confirmation_candidate(subject, body):
            continue

        # Skip if thread already tracked
        thread_id = lead["gmail_thread_id"]
        existing  = conn.execute(
            "SELECT id FROM appointments WHERE thread_id=? AND status != 'deleted'",
            (thread_id,)
        ).fetchone()
        if existing:
            continue

        try:
            messages = gm.get_thread_messages(creds, thread_id)
            data     = detect_confirmation(messages)
            if not data:
                continue
            conn.execute("""
                INSERT INTO appointments
                  (lead_id, thread_id, detected_at, status, meeting_type,
                   proposed_datetime, proposed_date_text, proposed_address,
                   client_name, client_email, partner_name, context_snippet, source, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'inbox',?,?)
            """, (
                lead["id"], thread_id, now, "pending",
                data.get("meeting_type"), data.get("proposed_datetime"),
                data.get("proposed_date_text"), data.get("proposed_address"),
                data.get("client_name") or lead.get("name"),
                data.get("client_email") or lead.get("from_email"),
                data.get("partner_name"), data.get("context_snippet"), now, now,
            ))
            conn.commit()
            print(f"[appt] Detected confirmation from inbox lead {lead['id']}: {data.get('context_snippet', '')[:60]}")
        except Exception as e:
            print(f"[appt] Detection error for lead {lead['id']}: {e}")

    # --- Sent mail ---
    try:
        sent_candidates = gm.scan_sent_for_confirmations()
        for item in sent_candidates:
            thread_id = item["thread_id"]
            existing  = conn.execute(
                "SELECT id FROM appointments WHERE thread_id=? AND status != 'deleted'",
                (thread_id,)
            ).fetchone()
            if existing:
                continue
            messages = gm.get_thread_messages(creds, thread_id)
            data     = detect_confirmation(messages)
            if not data:
                continue
            # Try to link to a lead via thread_id
            lead_row = conn.execute(
                "SELECT id FROM leads WHERE gmail_thread_id=?", (thread_id,)
            ).fetchone()
            lead_id = lead_row["id"] if lead_row else None
            conn.execute("""
                INSERT INTO appointments
                  (lead_id, thread_id, detected_at, status, meeting_type,
                   proposed_datetime, proposed_date_text, proposed_address,
                   client_name, client_email, partner_name, context_snippet, source, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'sent',?,?)
            """, (
                lead_id, thread_id, now, "pending",
                data.get("meeting_type"), data.get("proposed_datetime"),
                data.get("proposed_date_text"), data.get("proposed_address"),
                data.get("client_name"), data.get("client_email"),
                data.get("partner_name"), data.get("context_snippet"), now, now,
            ))
            conn.commit()
            print(f"[appt] Detected confirmation from sent mail thread {thread_id}: {data.get('context_snippet', '')[:60]}")
    except Exception as e:
        print(f"[appt] Sent scan error: {e}")

    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print(f"[lucilease] Started — http://localhost:8080  (poll every {POLL_SECS}s)")
    task = asyncio.create_task(_poll_loop())
    yield
    task.cancel()


app = FastAPI(title="Lucilease", version="0.3.0", lifespan=lifespan)


# ── Health ────────────────────────────────────────────────────────────────────

APP_VERSION = "0.4.2"

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


# ── Appointments ─────────────────────────────────────────────────────────────

@app.get("/api/appointments")
async def get_appointments(status: str = "pending"):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM appointments WHERE status=? ORDER BY detected_at DESC", (status,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/appointments/{appt_id}/accept")
async def accept_appointment(appt_id: int, body: dict = None):
    """
    Accept an appointment: create Google Calendar event + send confirmation email.
    body may contain: { "confirmed_datetime": "YYYY-MM-DDTHH:MM:SS" }
    """
    from ai import build_confirmation_email, get_agent_profile, mtype_label
    conn = get_conn()
    appt = conn.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
    cfg  = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM config").fetchall()}
    conn.close()

    if not appt:
        return {"ok": False, "error": "Appointment not found"}
    appt = dict(appt)

    creds = gm.get_credentials()
    if not creds:
        return {"ok": False, "error": "Gmail not connected"}

    timezone = cfg.get("timezone", "America/Los_Angeles")
    profile  = get_agent_profile()

    # Use confirmed_datetime override if provided, else fall back to proposed
    confirmed_body = body or {}
    dt_str         = confirmed_body.get("confirmed_datetime") or appt.get("proposed_datetime")
    confirmed_addr = confirmed_body.get("confirmed_address") or appt.get("proposed_address")

    # Build a human-readable version of the confirmed datetime for the email body
    confirmed_date_text = appt.get("proposed_date_text") or dt_str or "the scheduled time"
    if dt_str:
        try:
            import pytz, datetime as _dt2
            tz    = pytz.timezone(timezone)
            naive = _dt2.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            local = naive.astimezone(tz)
            confirmed_date_text = local.strftime("%A, %B %-d at %-I:%M %p")
        except Exception:
            pass  # fall back to proposed_date_text

    # Patch appt dict so build_confirmation_email uses confirmed values
    appt_confirmed = {**appt, "proposed_date_text": confirmed_date_text, "proposed_address": confirmed_addr}

    # Create calendar event
    calendar_event_id = None
    cal_error = None
    if dt_str:
        try:
            summary  = f"{mtype_label(appt.get('meeting_type')).title()} — {appt.get('client_name') or appt.get('client_email', 'Client')}"
            calendar_event_id = await asyncio.to_thread(
                cal.create_event, creds,
                summary, confirmed_addr or "", dt_str, timezone,
                description=appt.get("context_snippet") or "",
            )
        except Exception as e:
            cal_error = str(e)
            print(f"[appt] Calendar event creation failed: {e}")

    # Build confirmation email using confirmed datetime + address
    email_body = build_confirmation_email(appt_confirmed, profile)
    subject    = f"Confirmed: {mtype_label(appt.get('meeting_type')).title()}"
    now        = datetime.datetime.utcnow().isoformat() + "Z"
    email_error = None

    to_email = appt.get("client_email") or ""
    if to_email:
        # Try sending in-thread first; if Gmail rejects the thread_id (e.g. seeded/fake),
        # fall back to sending as a fresh email so the message always goes out.
        thread_id = appt.get("thread_id")
        sent = False
        if thread_id:
            try:
                await asyncio.to_thread(
                    gm.send_gmail_message, creds, to_email, subject, email_body,
                    thread_id=thread_id,
                )
                sent = True
            except Exception as e:
                print(f"[appt] In-thread send failed ({e}), retrying without thread_id...")
        if not sent:
            try:
                await asyncio.to_thread(
                    gm.send_gmail_message, creds, to_email, subject, email_body,
                )
            except Exception as e:
                email_error = str(e)
                print(f"[appt] Confirmation email send failed: {e}")
    else:
        email_error = "No client email on appointment"

    # Mark accepted + store event id (even if email/cal had errors — partial success)
    conn = get_conn()
    conn.execute("""
        UPDATE appointments
        SET status='accepted', calendar_event_id=?, updated_at=?
        WHERE id=?
    """, (calendar_event_id, now, appt_id))

    # Drop confirmation email into the Sent tab (drafts table, status='sent')
    if not email_error and to_email:
        conn.execute("""
            INSERT INTO drafts (lead_id, to_email, subject, body, status, created_at)
            VALUES (?,?,?,?,?,?)
        """, (appt.get("lead_id"), to_email, subject, email_body, "sent", now))

    conn.commit()
    conn.close()

    if email_error:
        return {"ok": False, "error": f"Appointment saved but email failed: {email_error}",
                "calendar_event_id": calendar_event_id,
                "email_sent": False, "cal_created": bool(calendar_event_id)}

    return {"ok": True, "calendar_event_id": calendar_event_id,
            "cal_warning": cal_error, "confirmed_date_text": confirmed_date_text,
            "email_sent": True, "cal_created": bool(calendar_event_id),
            "to_email": to_email}


@app.post("/api/appointments/{appt_id}/reject")
async def reject_appointment(appt_id: int):
    """Reject + auto-reply: Claude drafts alternative times and saves as draft."""
    from ai import draft_alternative_times
    now = datetime.datetime.utcnow().isoformat() + "Z"
    conn = get_conn()
    conn.execute(
        "UPDATE appointments SET status='rejected', updated_at=? WHERE id=?", (now, appt_id)
    )
    conn.commit()
    conn.close()
    try:
        result = await asyncio.to_thread(draft_alternative_times, appt_id)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.delete("/api/appointments/{appt_id}")
async def delete_appointment(appt_id: int):
    """Mark deleted. Returns thread messages + client info for compose modal."""
    conn = get_conn()
    appt = conn.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
    if not appt:
        conn.close()
        return {"ok": False, "error": "Not found"}
    appt = dict(appt)
    now  = datetime.datetime.utcnow().isoformat() + "Z"
    conn.execute("UPDATE appointments SET status='deleted', updated_at=? WHERE id=?", (now, appt_id))
    conn.commit()
    conn.close()

    thread_messages = []
    creds = gm.get_credentials()
    if creds and appt.get("thread_id"):
        try:
            thread_messages = await asyncio.to_thread(
                gm.get_thread_messages, creds, appt["thread_id"]
            )
        except Exception as e:
            print(f"[appt] Thread fetch on delete: {e}")

    return {
        "ok": True,
        "client_email": appt.get("client_email"),
        "client_name":  appt.get("client_name"),
        "thread_id":    appt.get("thread_id"),
        "subject":      appt.get("context_snippet") or "Follow-up",
        "messages":     thread_messages,
    }


# ── Calendar ──────────────────────────────────────────────────────────────────

@app.get("/api/calendar/events")
async def get_calendar_events():
    """Return merged events: accepted appointments from DB + Google Calendar (if connected)."""
    import datetime as _dt

    # Always pull accepted appointments from local DB
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM appointments WHERE status='accepted' ORDER BY proposed_datetime ASC"
    ).fetchall()
    conn.close()

    local_events = []
    for r in rows:
        r = dict(r)
        local_events.append({
            "summary":   f"{(r.get('meeting_type') or 'Appointment').replace('_',' ').title()} — {r.get('client_name') or r.get('client_email') or 'Client'}",
            "start":     r.get("proposed_datetime"),
            "location":  r.get("proposed_address") or "",
            "lucilease": True,
            "appt_id":   r.get("id"),
        })

    # Try to merge Google Calendar events
    gcal_events = []
    creds = gm.get_credentials()
    if creds:
        try:
            gcal_events = await asyncio.to_thread(cal.list_upcoming_events, creds)
        except Exception as e:
            print(f"[calendar] Google Calendar fetch failed: {e}")

    # Merge: local first, then Google Calendar (dedup by calendar_event_id if present)
    all_events = local_events + [e for e in gcal_events if not e.get("lucilease")]
    # Sort by start
    def _sort_key(e):
        try: return e.get("start") or ""
        except: return ""
    all_events.sort(key=_sort_key)

    return {"ok": True, "events": all_events}


# ── Static + SPA ──────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    return FileResponse(str(STATIC / "index.html"))

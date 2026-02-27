"""
main.py — Lucilease FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import pathlib
import datetime

from db import init_db, get_conn

app = FastAPI(title="Lucilease", version="0.1.0")

STATIC = pathlib.Path(__file__).parent / "static"


@app.on_event("startup")
async def on_startup():
    init_db()
    print("[lucilease] Started. http://localhost:8080")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.datetime.utcnow().isoformat() + "Z"}


# ── Stats (dashboard counters) ────────────────────────────────────────────────

@app.get("/api/stats")
async def stats():
    conn = get_conn()
    cur = conn.cursor()
    leads_new    = cur.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
    leads_total  = cur.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    clients      = cur.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    properties   = cur.execute("SELECT COUNT(*) FROM properties WHERE status='active'").fetchone()[0]
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
        "SELECT * FROM leads WHERE status=? ORDER BY first_seen_at DESC",
        (status,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Clients ───────────────────────────────────────────────────────────────────

@app.get("/api/clients")
async def get_clients():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM clients ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Properties ────────────────────────────────────────────────────────────────

@app.get("/api/properties")
async def get_properties():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM properties WHERE status='active' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Static + SPA fallback ─────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    return FileResponse(str(STATIC / "index.html"))

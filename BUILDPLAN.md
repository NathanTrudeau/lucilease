# Lucilease — Build Plan v1

_Written by Luci. Last updated: 2026._

---

## What We're Building

A local web app served by Docker. The user runs `docker compose up`, opens their browser to `http://localhost:8080`, and that is Lucilease. No terminal after that. No installs beyond Docker Desktop.

Works on Windows and Mac (Docker Desktop handles both).

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python (FastAPI) | Already in the repo, async, lightweight |
| Frontend | HTML + vanilla JS (HTMX) | No build step, no Node, simple to ship |
| Database | SQLite | Portable, zero-config, already in spec |
| Email | Gmail API (OAuth2) | Draft creation, label filtering |
| Calendar | Google Calendar API (OAuth2) | Same OAuth flow as Gmail |
| AI | Anthropic Claude Sonnet | Already configured |
| Container | Docker + docker compose | Portability + packaging |

---

## Feature Scope — v1

### 1. Setup Wizard (First Run)
- Detects if Gmail is not yet authenticated
- Guides user through Google OAuth (browser popup, click Allow, done)
- Collects: agent name, company name, reply tone/style preference
- Optional: inbox label filters
- Saves config to `config.yaml` + secrets to `.env`

### 2. Inbox Panel
- Polls Gmail for new lead emails on a schedule (configurable, default 5 min)
- Parses and displays leads: sender name, email, phone (if found), message summary
- Deduplication via fingerprint (email + phone SHA256)
- Per-lead actions:
  - **Draft Reply** — Claude writes a personalized reply, saves to Gmail Drafts
  - **Mark Handled** — removes from active view, logs to DB
  - **Add to Clients** — saves parsed contact to client list

### 3. Client List
- SQLite table: name, email, phone, address, notes, date added, status
- Auto-populated when "Add to Clients" is clicked from inbox
- Manual add/edit/delete
- Search + filter

### 4. Property List
- SQLite table: address, type (rental/sale), bedrooms, bathrooms, price, status (active/pending/sold), notes
- Manual add/edit/delete
- Linked to clients (which agent is showing which property)

### 5. Calendar Panel
- Shows upcoming week from Google Calendar
- Per-email action: "Schedule Appointment" — reads the email, suggests a time, creates a calendar event with 1hr alert
- Events created with title, client name, property address (if known)

### 6. Draft Reply Engine
- Claude Sonnet writes the reply using:
  - Agent profile (name, company, tone)
  - Parsed lead info (what they're looking for, budget, timeline)
  - Relevant properties from the property list (if match found)
- Draft lands in Gmail Drafts — agent reviews and sends manually
- Auto-send toggle (off by default) with daily summary email

---

## What We're NOT Building in v1
- Salesforce integration (later)
- Property website scanner (dropped — legal risk)
- Multi-email providers beyond Gmail (Outlook/Yahoo = v2)
- Multi-user / multi-tenant (single agent per install)
- Mobile UI

---

## Build Phases

### Phase 0 — Foundation (current state → working Docker web app)
- [ ] Fix Dockerfile COPY path bug (`../src` → `src`)
- [ ] Replace `main.py` polling loop with FastAPI app
- [ ] Basic HTML shell at `localhost:8080` with Lucilease branding
- [ ] SQLite schema: clients, properties, leads, config
- [ ] Health check endpoint

### Phase 1 — Gmail + Inbox
- [ ] Google OAuth2 setup (credentials via `.env`)
- [ ] Gmail polling service (background thread)
- [ ] Lead parsing (upgrade to Pydantic model)
- [ ] Inbox panel UI
- [ ] Dedup logic (already exists, migrate to DB)

### Phase 2 — Draft Replies
- [ ] Claude Sonnet integration for reply drafting
- [ ] Agent profile config (name, company, tone)
- [ ] Draft → Gmail Drafts via API
- [ ] Property matching (suggest relevant listings in reply)

### Phase 3 — Client & Property Lists
- [ ] Client list CRUD UI
- [ ] Property list CRUD UI
- [ ] Auto-populate client from inbox action

### Phase 4 — Calendar
- [ ] Google Calendar OAuth (same flow, additional scope)
- [ ] Calendar view panel
- [ ] "Schedule from email" action

### Phase 5 — Polish + First Deployment
- [ ] Setup wizard (first-run detection)
- [ ] `.env.example` + README + RUNBOOK
- [ ] Daily summary email (optional auto-send digest)
- [ ] Windows + Mac Docker Desktop testing

---

## File Structure (target)

```
lucilease/
├── docker/
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
├── config/
│   └── config.yaml
├── data/                    # Docker volume (SQLite + seen.json)
├── fixtures/                # Test emails
├── src/
│   ├── main.py              # FastAPI app entry
│   ├── db.py                # SQLite setup + models
│   ├── gmail.py             # Gmail API connector
│   ├── calendar.py          # Google Calendar connector
│   ├── ai.py                # Claude draft engine
│   ├── leads.py             # Lead parsing + dedup
│   └── static/
│       ├── index.html       # Main UI shell
│       └── app.js           # Frontend logic
├── LUCILEASE_SPEC.md
└── BUILDPLAN.md             # This file
```

---

## First Deployment (Family Friend)

- You host it (VPS or your machine, port-forwarded or tunneled via ngrok/Cloudflare Tunnel)
- They access it via browser at your provided URL
- You handle setup wizard for them on first run
- They get Gmail OAuth'd and configured, then it just runs
- No technical knowledge required from them after setup

---

## Notes

- Keep polling conservative — Gmail API has quotas. 5-minute poll is fine.
- Never auto-send by default. Draft-only is the safe, trusted baseline.
- All secrets in `.env`, never committed to git.
- SQLite file lives in the `/data` Docker volume — persists across restarts.

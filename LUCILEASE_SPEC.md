# Lucilease Spec (v1)

Goal: 24/7 realtor ops autopilot that ingests Gmail leads, dedupes, and upserts Salesforce Leads. Draft replies only by default.

Deliverables:
- Dockerized service runnable via docker compose on Windows 11
- config.yaml + .env.example
- Gmail OAuth connector (read + create draft)
- Salesforce connected-app OAuth connector + Lead upsert
- Lead schema (pydantic) + dedupe store (SQLite first)
- Tests (fixtures for emails + mocked Salesforce)
- README + RUNBOOK

Guardrails:
- No UI.
- Do not modify files outside this repo.
- Default draft-only.
- Be conservative with polling and rate limits.
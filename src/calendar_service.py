"""
calendar_service.py — Google Calendar integration for Lucilease.

Uses the same OAuth credentials/token as gmail.py.
Requires the calendar.events scope (added in v0.4.2).
"""

import datetime
from googleapiclient.discovery import build


def get_service(creds):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_event(creds, summary: str, location: str, start_dt: str,
                 timezone: str, description: str = "") -> str:
    """
    Create a 1-hour calendar event with a 30-min popup reminder.
    start_dt: ISO 8601 string (e.g. '2025-03-10T14:00:00')
    Returns the created event id.
    """
    service = get_service(creds)
    start = datetime.datetime.fromisoformat(start_dt)
    end   = start + datetime.timedelta(hours=1)

    event = {
        "summary":     summary,
        "location":    location or "",
        "description": f"{description}\n\n[Scheduled via Lucilease]".strip(),
        "start": {"dateTime": start.isoformat(), "timeZone": timezone},
        "end":   {"dateTime": end.isoformat(),   "timeZone": timezone},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 30}],
        },
    }
    result = service.events().insert(calendarId="primary", body=event).execute()
    print(f"[calendar] Created event '{summary}' → {result['id']}")
    return result["id"]


def list_upcoming_events(creds, max_results: int = 25) -> list[dict]:
    """Fetch upcoming events from primary calendar, sorted by start time."""
    service = get_service(creds)
    now = datetime.datetime.utcnow().isoformat() + "Z"
    result = service.events().list(
        calendarId="primary",
        timeMin=now,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = []
    for e in result.get("items", []):
        start = e["start"].get("dateTime", e["start"].get("date", ""))
        end   = e["end"].get("dateTime",   e["end"].get("date", ""))
        desc  = e.get("description", "")
        events.append({
            "id":          e["id"],
            "summary":     e.get("summary", "(No title)"),
            "location":    e.get("location", ""),
            "start":       start,
            "end":         end,
            "description": desc,
            "lucilease":   "[Scheduled via Lucilease]" in desc,
        })
    return events


def get_free_busy(creds, days_ahead: int = 14) -> list[dict]:
    """Return busy blocks for primary calendar over the next N days."""
    service = get_service(creds)
    now = datetime.datetime.utcnow()
    end = now + datetime.timedelta(days=days_ahead)
    result = service.freebusy().query(body={
        "timeMin": now.isoformat() + "Z",
        "timeMax": end.isoformat() + "Z",
        "items":   [{"id": "primary"}],
    }).execute()
    return result.get("calendars", {}).get("primary", {}).get("busy", [])

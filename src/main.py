import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

RUN_ONCE = os.getenv("RUN_ONCE", "0") == "1"
POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    log("Lucilease v1 starting (fixture mode).")
    while True:
        run_once()
        time.sleep(POLL)
import os, time, datetime, pathlib, re, hashlib, json

BASE = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = BASE / "fixtures"
DATA = pathlib.Path("/data")  # docker volume mount
SEEN_FILE = DATA / "seen.json"

POLL = int(os.getenv("POLL_SECONDS", "10"))

def utc():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def fingerprint(email: str, phone: str) -> str:
    raw = (email.strip().lower() + "|" + re.sub(r"\D", "", phone or "")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def parse_fixture_email(text: str) -> dict:
    # Very simple extraction to start; we’ll evolve this into pydantic + better parsing next.
    def find(prefix):
        m = re.search(rf"^{re.escape(prefix)}\s*:\s*(.+)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    from_email = find("From") or ""
    name = find("Name") or ""
    phone = find("Phone") or ""
    subject = find("Subject") or ""

    # naive budget extraction
    budget = None
    m = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*)(?:\s*/\s*month|\s*per month|/month|/mo|month)?", text, flags=re.IGNORECASE)
    if m:
        budget = int(m.group(1).replace(",", ""))

    lead = {
        "source": "fixture",
        "from_email": from_email,
        "name": name,
        "phone": phone,
        "subject": subject,
        "budget_monthly_usd_guess": budget,
        "raw_excerpt": text.strip()[:600],
        "first_seen_at": utc(),
        "fingerprint": fingerprint(from_email, phone),
    }
    return lead

def log(msg):
    print(f"[{utc()}] {msg}", flush=True)

def run_once():
    seen = load_seen()
    if not FIXTURES.exists():
        log(f"fixtures folder not found: {FIXTURES}")
        return

    for p in sorted(FIXTURES.glob("email_*.txt")):
        key = p.name
        if key in seen:
            continue

        text = p.read_text(encoding="utf-8")
        lead = parse_fixture_email(text)

        # "Salesforce sink (stub)" = just print JSON for now
        log(f"NEW LEAD -> would upsert to Salesforce: {lead['from_email']} ({lead['fingerprint'][:10]}...)")
        print(json.dumps(lead, indent=2), flush=True)

        seen.add(key)

    save_seen(seen)

if __name__ == "__main__":
    RUN_ONCE = os.getenv("RUN_ONCE", "0") == "1"
    log(f"Lucilease v1 starting (fixture mode). RUN_ONCE={RUN_ONCE}")

    run_once()

    if RUN_ONCE:
        log("RUN_ONCE complete. Exiting.")
        raise SystemExit(0)

    while True:
        time.sleep(POLL)
        run_once()
#!/usr/bin/env python3
"""
fix_stale_inbox.py — Mark leads with accepted appointments as 'replied'
so they stop appearing in the inbox. One-time patch for pre-v0.4.16 data.
"""
import os, sys
sys.path.insert(0, '/app')
from db import get_conn

conn = get_conn()
cur = conn.execute("""
    UPDATE leads SET status='replied'
    WHERE id IN (
        SELECT DISTINCT l.id FROM leads l
        JOIN appointments a ON a.lead_id = l.id
        WHERE a.status = 'accepted'
        AND l.status IN ('new','drafted')
    )
""")
conn.commit()
print(f"✅ Fixed {cur.rowcount} stale lead(s) — they will no longer appear in inbox.")
conn.close()

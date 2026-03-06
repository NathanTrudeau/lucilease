#!/usr/bin/env python3
"""
reset_all.py — Nuclear reset. Wipes ALL data, keeps schema.

Clears: leads, appointments, drafts, clients, properties,
        open_house_slots, config

Run:
  docker exec -it lucilease python /scripts/reset_all.py
"""
import sqlite3, os

DB_PATH = os.environ.get("DB_PATH", "/data/lucilease.db")

TABLES = [
    "appointments",
    "drafts",
    "leads",
    "open_house_slots",
    "clients",
    "properties",
    "config",
]

def main():
    conn = sqlite3.connect(DB_PATH)
    for t in TABLES:
        conn.execute(f"DELETE FROM {t}")
        print(f"🗑  Cleared: {t}")
    conn.commit()
    conn.close()
    print("\n✅ Full reset complete. DB is empty — schema intact.")
    print("   Restart the container and go through Settings to re-connect Gmail.")

if __name__ == "__main__":
    main()

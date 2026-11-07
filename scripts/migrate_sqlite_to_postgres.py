from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Heidi SQLite leads to managed PostgreSQL.")
    parser.add_argument("--source", default="data/heidi_leads.db")
    parser.add_argument("--database-url")
    parser.add_argument("--apply", action="store_true", help="Write rows; otherwise perform a dry run.")
    args = parser.parse_args()

    source = sqlite3.connect(Path(args.source))
    source.row_factory = sqlite3.Row
    rows = source.execute("SELECT * FROM leads ORDER BY created_at, id").fetchall()
    if not args.apply:
        print(json.dumps({"source_leads": len(rows), "berlin": sum(row[1] == "Berlin" and row[2] == "Germany" for row in rows), "frankfurt": sum(row[1] == "Frankfurt" and row[2] == "Germany" for row in rows), "mode": "dry-run"}))
        return
    if not args.database_url:
        parser.error("--database-url is required with --apply")
    os.environ["DATABASE_URL"] = args.database_url
    from app import db

    db.init_db()
    with db.connect() as destination:
        existing = {row[0] for row in destination.execute("SELECT id FROM leads").fetchall()} if args.apply else set()
    print(json.dumps({"source_leads": len(rows), "existing_destination_ids": len(existing), "mode": "apply"}))

    inserted = 0
    updated = 0
    for row in rows:
        item = dict(row)
        for key in ("evidence_json", "gaps_json", "sources_json", "raw_json"):
            target = key.removesuffix("_json")
            item[target] = json.loads(item.pop(key) or ("{}" if target == "raw" else "[]"))
        before = item["id"] in existing
        db.upsert_lead(item)
        updated += int(before)
        inserted += int(not before)
    print(json.dumps({"inserted": inserted, "updated": updated, "destination_leads": len(db.list_leads(limit=5000))}))


if __name__ == "__main__":
    main()
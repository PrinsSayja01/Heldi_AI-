from __future__ import annotations
import json, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from . import config


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    if config.DATABASE_URL:
        from .postgres import Connection
        return Connection(config.DATABASE_URL)
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
          id TEXT PRIMARY KEY,
          city TEXT NOT NULL,
          country TEXT NOT NULL,
          name TEXT NOT NULL,
          website TEXT,
          domain TEXT,
          address TEXT,
          weg_management TEXT DEFAULT 'Unknown',
          rental_management TEXT DEFAULT 'Unknown',
          special_management TEXT DEFAULT 'Unknown',
          portfolio_units INTEGER,
          portfolio_buildings INTEGER,
          digital_portal TEXT DEFAULT 'Unknown',
          vdiv_member TEXT DEFAULT 'Unknown',
          contact_person TEXT,
          contact_role TEXT,
          contact_email TEXT,
          email_type TEXT,
          phone TEXT,
          service_evidence_status TEXT,
          metering_signal TEXT DEFAULT 'Unknown',
          summary TEXT,
          rationale TEXT,
          score INTEGER DEFAULT 0,
          tier TEXT DEFAULT 'Research',
          completeness INTEGER DEFAULT 0,
          confidence TEXT DEFAULT 'Low',
          status TEXT DEFAULT 'New',
          notes TEXT DEFAULT '',
          evidence_json TEXT DEFAULT '[]',
          gaps_json TEXT DEFAULT '[]',
          sources_json TEXT DEFAULT '[]',
          raw_json TEXT DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(city, country, domain)
        );
        CREATE INDEX IF NOT EXISTS idx_leads_city ON leads(city, country);
        CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC);
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,
          city TEXT NOT NULL,
          country TEXT NOT NULL,
          status TEXT NOT NULL,
          progress INTEGER NOT NULL DEFAULT 0,
          current_step TEXT,
          found INTEGER DEFAULT 0,
          processed INTEGER DEFAULT 0,
          total INTEGER DEFAULT 0,
          error TEXT,
          logs_json TEXT DEFAULT '[]',
          started_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS app_settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """)
    seed_berlin_if_empty()


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def seed_berlin_if_empty() -> None:
    if not config.SEED_PATH.exists():
        return
    with connect() as db:
        existing = db.execute("SELECT COUNT(*) FROM leads WHERE city='Berlin' AND country='Germany'").fetchone()[0]
        if existing:
            return
        try:
            rows = json.loads(config.SEED_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        for r in rows:
            name = str(r.get("Company") or "Unknown company").strip()
            email = r.get("Published Business Email")
            contact = r.get("Contact Person")
            original_score = int(float(r.get("Lead Fit Score / 100") or 0))
            service_points = min(35, (15 if r.get("WEG Management") == "Yes" else 0) + (15 if r.get("Rental Management") == "Yes" else 0) + (5 if r.get("Sondereigentum Management") == "Yes" else 0))
            quality = str(r.get("Contact Quality") or "")
            email_type_text = str(r.get("Email Type") or "")
            if r.get("Contact Person") and ("personal" in quality.lower() or "personal" in email_type_text.lower() or "direct" in email_type_text.lower()): contact_points = 20
            elif r.get("Contact Person"): contact_points = 13
            elif r.get("Published Business Email"): contact_points = 8
            elif r.get("Website"): contact_points = 4
            else: contact_points = 0
            # Seed rows are not re-crawled yet, so portfolio, metering signal and fresh evidence points remain zero.
            score = service_points + contact_points
            score_breakdown = {"service_fit": service_points, "portfolio_scale": 0, "contact_quality": contact_points, "metering_signal": 0, "evidence_quality": 0}
            sources = []
            for u in [r.get("Company Evidence URL"), r.get("Contact Evidence URL")]:
                if u and u not in [s.get("url") for s in sources]:
                    sources.append({"url": u, "title": "Seed research source", "type": "directory", "snippet": r.get("Source Notes", "")})
            db.execute("""INSERT OR IGNORE INTO leads (
              id,city,country,name,website,domain,address,weg_management,rental_management,special_management,
              vdiv_member,contact_person,contact_role,contact_email,email_type,phone,service_evidence_status,
              summary,rationale,score,tier,completeness,confidence,status,notes,evidence_json,gaps_json,sources_json,raw_json,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
              str(r.get("Lead ID") or uuid.uuid4().hex[:10]), "Berlin", "Germany", name,
              r.get("Website"), _domain(r.get("Website")), r.get("Business Address"),
              r.get("WEG Management") or "Unknown", r.get("Rental Management") or "Unknown",
              r.get("Sondereigentum Management") or "Unknown", r.get("VDIV Member") or "Unknown",
              contact, r.get("Contact Role / Seniority"), email,
              ("generic" if "generic" in str(r.get("Email Type") or "").lower() else "personal_work" if "personal" in quality.lower() else "unknown" if email else None), r.get("Phone"),
              r.get("Service Evidence Status"), r.get("Metering Use-Case Rationale"),
              r.get("Metering Use-Case Rationale"), score, _tier(score),
              _seed_completeness(r), "Low", "Seeded",
              f"Imported from the 06 Nov 2026 case-study workbook. Re-score uses the current 100-point framework; original workbook score ({original_score}) is preserved in the source record. Revalidate before outreach.",
              _json([]), _json(_seed_gaps(r)), _json(sources), _json({**r, "original_workbook_score": original_score, "score_breakdown": score_breakdown}), now_iso(), now_iso()
            ))


def _domain(url: str | None) -> str | None:
    if not url: return None
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return host or None


def _tier(score: int) -> str:
    return "Tier 1" if score >= 80 else "Tier 2" if score >= 60 else "Tier 3"


def _seed_completeness(r: dict) -> int:
    address = str(r.get("Business Address") or "")
    portfolio = str(r.get("Portfolio Size Evidence") or "")
    weighted = [
        (bool(address and address.lower() not in ("berlin", "berlin (street address not captured in first pass)")), 1),
        (bool(r.get("Website")), 1),
        (r.get("WEG Management") in ("Yes", "No"), 1),
        (r.get("Rental Management") in ("Yes", "No"), 1),
        (r.get("Sondereigentum Management") in ("Yes", "No"), 1),
        (bool(portfolio and "not found" not in portfolio.lower() and "not disclosed" not in portfolio.lower()), 2),
        (bool(r.get("Contact Person")), 1),
        (bool(r.get("Published Business Email")), 1),
        (bool(r.get("Phone")), 1),
        (bool(r.get("Contact Role / Seniority")), 1),
        (r.get("VDIV Member") in ("Yes", "No"), 1),
        (False, 2),  # Metering signals were not re-researched in the seed import.
        (False, 2),  # No source excerpts have yet been validated by the new crawler.
    ]
    return round(sum(weight for present, weight in weighted if present) / sum(weight for _, weight in weighted) * 100)


def _seed_gaps(r: dict) -> list[str]:
    return [x for x in [
      "Managed residential units/buildings not publicly confirmed" if not r.get("Portfolio Size Evidence") or "Not found" in str(r.get("Portfolio Size Evidence")) else None,
      "Confirm who selects the metering provider",
      "Confirm incumbent metering provider and contract renewal date",
      "Revalidate contact and service information before outreach"
    ] if x]


def lead_from_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("evidence_json", "gaps_json", "sources_json", "raw_json"):
        try: d[key.replace("_json", "")] = json.loads(d.pop(key) or "[]")
        except Exception: d[key.replace("_json", "")] = []
    return d


def list_leads(city: str | None = None, country: str | None = None, q: str = "", tier: str = "", status: str = "", limit: int = 500) -> list[dict]:
    sql = "SELECT * FROM leads WHERE 1=1"
    args: list[Any] = []
    if city: sql += " AND lower(city)=lower(?)"; args.append(city)
    if country: sql += " AND lower(country)=lower(?)"; args.append(country)
    if q:
        sql += " AND (lower(name) LIKE ? OR lower(coalesce(address,'')) LIKE ? OR lower(coalesce(contact_person,'')) LIKE ? OR lower(coalesce(domain,'')) LIKE ?)"
        like = f"%{q.lower()}%"; args += [like, like, like, like]
    if tier: sql += " AND tier=?"; args.append(tier)
    if status: sql += " AND status=?"; args.append(status)
    sql += " ORDER BY score DESC, name COLLATE NOCASE LIMIT ?"; args.append(max(1,min(limit,2000)))
    with connect() as db:
        return [lead_from_row(r) for r in db.execute(sql, args).fetchall()]


def get_lead(lead_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        return lead_from_row(row) if row else None


def upsert_lead(payload: dict) -> str:
    city, country = payload.get("city", "Berlin"), payload.get("country", "Germany")
    name = payload.get("name") or "Unknown company"
    domain = payload.get("domain") or _domain(payload.get("website"))
    with connect() as db:
        existing = None
        if domain:
            existing = db.execute("SELECT id FROM leads WHERE lower(city)=lower(?) AND lower(country)=lower(?) AND lower(domain)=lower(?)", (city,country,domain)).fetchone()
        if not existing:
            existing = db.execute("SELECT id FROM leads WHERE lower(city)=lower(?) AND lower(country)=lower(?) AND lower(name)=lower(?) ORDER BY updated_at DESC LIMIT 1", (city,country,name)).fetchone()
        if existing:
            lead_id = existing[0]
        else:
            lead_id = payload.get("id") or uuid.uuid4().hex[:12]
        values = {
          "id": lead_id,"city":city,"country":country,"name":name,"website":payload.get("website"),"domain":domain,
          "address":payload.get("address"),"weg_management":payload.get("weg_management","Unknown"),
          "rental_management":payload.get("rental_management","Unknown"),"special_management":payload.get("special_management","Unknown"),
          "portfolio_units":payload.get("portfolio_units"),"portfolio_buildings":payload.get("portfolio_buildings"),
          "digital_portal":payload.get("digital_portal","Unknown"),"vdiv_member":payload.get("vdiv_member","Unknown"),
          "contact_person":payload.get("contact_person"),"contact_role":payload.get("contact_role"),
          "contact_email":payload.get("contact_email"),"email_type":payload.get("email_type"),"phone":payload.get("phone"),
          "service_evidence_status":payload.get("service_evidence_status"),"metering_signal":payload.get("metering_signal","Unknown"),
          "summary":payload.get("summary"),"rationale":payload.get("rationale"),"score":int(payload.get("score",0)),
          "tier":payload.get("tier",_tier(int(payload.get("score",0)))),"completeness":int(payload.get("completeness",0)),
          "confidence":payload.get("confidence","Low"),"status":payload.get("status","New"),"notes":payload.get("notes",""),
          "evidence_json":_json(payload.get("evidence",[])),"gaps_json":_json(payload.get("gaps",[])),
          "sources_json":_json(payload.get("sources",[])),"raw_json":_json(payload.get("raw",{})),"created_at":payload.get("created_at",now_iso()),"updated_at":now_iso()
        }
        cols = list(values.keys())
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("id","created_at"))
        db.execute(f"INSERT INTO leads ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) ON CONFLICT(id) DO UPDATE SET {updates}", [values[c] for c in cols])
    return lead_id


def update_lead_fields(lead_id: str, fields: dict) -> bool:
    allowed = {"status", "notes", "contact_person", "contact_role", "contact_email", "email_type", "phone", "portfolio_units", "portfolio_buildings", "vdiv_member"}
    fields = {k:v for k,v in fields.items() if k in allowed}
    if not fields: return False
    fields["updated_at"] = now_iso()
    with connect() as db:
        cur = db.execute(f"UPDATE leads SET {','.join(f'{k}=?' for k in fields)} WHERE id=?", [*fields.values(),lead_id])
        return cur.rowcount > 0


def city_stats() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT city,country,COUNT(*) total,SUM(CASE WHEN tier='Tier 1' THEN 1 ELSE 0 END) tier1, SUM(CASE WHEN contact_person IS NOT NULL AND contact_person!='' THEN 1 ELSE 0 END) named_contacts, SUM(CASE WHEN contact_email IS NOT NULL AND contact_email!='' THEN 1 ELSE 0 END) emails FROM leads GROUP BY city,country ORDER BY city").fetchall()
        return [dict(r) for r in rows]


def create_job(job_id: str, city: str, country: str, total: int) -> None:
    with connect() as db:
        db.execute("INSERT INTO jobs (id,city,country,status,progress,total,started_at,updated_at) VALUES (?,?,?,'queued',0,?,?,?)", (job_id,city,country,total,now_iso(),now_iso()))


def update_job(job_id: str, **fields) -> None:
    allowed = {"status","progress","current_step","found","processed","total","error","logs_json","finished_at"}
    fields = {k:(json.dumps(v,ensure_ascii=False) if k=="logs_json" and not isinstance(v,str) else v) for k,v in fields.items() if k in allowed}
    fields["updated_at"] = now_iso()
    with connect() as db:
        db.execute(f"UPDATE jobs SET {','.join(f'{k}=?' for k in fields)} WHERE id=?", [*fields.values(),job_id])


def get_job(job_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row: return None
        d = dict(row)
        try: d["logs"] = json.loads(d.pop("logs_json") or "[]")
        except Exception: d["logs"] = []
        return d


def list_jobs(city: str | None = None, country: str | None = None, limit: int = 20) -> list[dict]:
    sql = "SELECT * FROM jobs WHERE 1=1"
    args: list[Any] = []
    if city:
        sql += " AND lower(city)=lower(?)"; args.append(city)
    if country:
        sql += " AND lower(country)=lower(?)"; args.append(country)
    sql += " ORDER BY started_at DESC LIMIT ?"; args.append(max(1, min(limit, 100)))
    with connect() as db:
        jobs = []
        for row in db.execute(sql, args).fetchall():
            item = dict(row)
            try: item["logs"] = json.loads(item.pop("logs_json") or "[]")
            except Exception: item["logs"] = []
            jobs.append(item)
        return jobs


def get_setting(key: str, default: str = "") -> str:
    with connect() as db:
        row=db.execute("SELECT value FROM app_settings WHERE key=?",(key,)).fetchone()
        return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with connect() as db:
        db.execute("INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(key,value,now_iso()))

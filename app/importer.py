from __future__ import annotations
import csv
import io
import json
import re
from typing import Any
from urllib.parse import urlparse
from . import db


def _normalize_domain(url_or_domain: str) -> str:
    if not url_or_domain:
        return ""
    val = url_or_domain.strip().lower()
    if "://" not in val:
        val = "http://" + val
    try:
        p = urlparse(val)
        host = (p.hostname or "").split(":")[0].removeprefix("www.")
        parts = host.split(".")
        if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "gov"} and len(parts[-1]) == 2:
            return ".".join(parts[-3:])
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return ""


def parse_import_content(content_bytes: bytes, filename: str) -> list[dict]:
    """Parses uploaded CSV or JSON file into candidate dictionaries."""
    fname = filename.lower()
    if fname.endswith(".json"):
        text = content_bytes.decode("utf-8", errors="replace")
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
            return data["items"]
        raise ValueError("JSON file must contain an array of lead objects.")
    
    # Try CSV
    text = content_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for r in reader:
        if any(v.strip() for v in r.values() if v):
            rows.append(r)
    return rows


def map_row_to_lead_candidate(row: dict, default_city: str, default_country: str) -> dict:
    """Standardizes column names and maps various CSV/JSON formats into lead schema."""
    # Find keys case-insensitively
    low = {k.strip().lower(): v for k, v in row.items() if k}
    
    company_name = (
        low.get("company") or low.get("company name") or low.get("company_name") or
        low.get("name") or low.get("firmenname") or "Unknown Company"
    ).strip()
    
    city = (low.get("city") or low.get("stadt") or default_city).strip()
    country = (low.get("country") or low.get("land") or default_country).strip()
    
    website = (low.get("website") or low.get("web") or low.get("url") or low.get("homepage") or "").strip()
    domain = (low.get("domain") or _normalize_domain(website)).strip()
    if website and not website.startswith("http"):
        website = f"https://{website}"

    address = (low.get("address") or low.get("adresse") or low.get("street") or "").strip() or None
    
    # Service flags
    def _flag(k_list):
        for k in k_list:
            if k in low:
                val = str(low[k]).strip().lower()
                if val in ("yes", "ja", "true", "1"):
                    return "Yes"
                if val in ("no", "nein", "false", "0"):
                    return "No"
        return "Unknown"

    weg = _flag(["weg_management", "weg management", "weg", "weg-verwaltung"])
    rental = _flag(["rental_management", "rental management", "mietverwaltung", "rental"])
    special = _flag(["special_management", "sondereigentum management", "sondereigentumsverwaltung", "sev"])

    # Portfolio units
    def _int(k_list):
        for k in k_list:
            if k in low and str(low[k]).strip():
                clean = re.sub(r"[^\d]", "", str(low[k]))
                if clean.isdigit():
                    return int(clean)
        return None

    units = _int(["portfolio_units", "disclosed portfolio (units)", "units", "wohneinheiten", "portfolio"])
    buildings = _int(["portfolio_buildings", "buildings", "gebäude"])

    contact_person = (low.get("contact_person") or low.get("contact person") or low.get("contact") or low.get("ansprechpartner") or "").strip() or None
    contact_role = (low.get("contact_role") or low.get("contact role") or low.get("role") or low.get("position") or "").strip() or None
    contact_email = (low.get("contact_email") or low.get("published business email") or low.get("email") or "").strip().lower() or None
    email_type = (low.get("email_type") or low.get("email type") or ("personal_work" if contact_person and contact_email and any(part in contact_email for part in contact_person.lower().split() if len(part)>2) else "generic" if contact_email else None))
    phone = (low.get("phone") or low.get("telefon") or "").strip() or None

    metering_signal = (low.get("metering_signal") or low.get("metering") or "Unknown").strip().capitalize()
    if metering_signal not in ("High", "Medium", "Low", "Unknown"):
        metering_signal = "Unknown"

    status = (low.get("status") or low.get("sales status") or "New").strip()
    notes = (low.get("notes") or low.get("review notes") or "").strip()

    return {
        "city": city,
        "country": country,
        "name": company_name,
        "website": website or None,
        "domain": domain or None,
        "address": address,
        "weg_management": weg,
        "rental_management": rental,
        "special_management": special,
        "portfolio_units": units,
        "portfolio_buildings": buildings,
        "contact_person": contact_person,
        "contact_role": contact_role,
        "contact_email": contact_email,
        "email_type": email_type,
        "phone": phone,
        "metering_signal": metering_signal,
        "status": status,
        "notes": notes,
        "service_evidence_status": "Imported user dataset",
        "completeness": 40 if contact_email and (weg == "Yes" or rental == "Yes") else 20,
        "confidence": "Medium" if (units or contact_person) else "Low"
    }


def preview_import(content_bytes: bytes, filename: str, default_city: str, default_country: str) -> dict:
    rows = parse_import_content(content_bytes, filename)
    candidates = [map_row_to_lead_candidate(r, default_city, default_country) for r in rows]
    
    # Check duplicates against existing database
    existing_domains = set()
    existing_names = set()
    for item in db.list_leads(limit=5000):
        if item.get("domain"):
            existing_domains.add((item["city"].lower(), item["country"].lower(), item["domain"].lower()))
        if item.get("name"):
            existing_names.add((item["city"].lower(), item["country"].lower(), item["name"].lower()))
            
    analyzed = []
    new_count = 0
    dup_count = 0
    for c in candidates:
        domain_key = (c["city"].lower(), c["country"].lower(), (c["domain"] or "").lower())
        name_key = (c["city"].lower(), c["country"].lower(), c["name"].lower())
        is_dup = (c.get("domain") and domain_key in existing_domains) or (name_key in existing_names)
        if is_dup:
            dup_count += 1
            analyzed.append({**c, "_is_duplicate": True, "_dup_reason": "Matches existing domain or company name in this market"})
        else:
            new_count += 1
            analyzed.append({**c, "_is_duplicate": False})

    return {
        "total_parsed": len(candidates),
        "new_count": new_count,
        "duplicate_count": dup_count,
        "preview_items": analyzed[:50],  # first 50 rows for preview inspection
        "all_items": analyzed
    }


def commit_import(items: list[dict], overwrite_duplicates: bool = False) -> dict:
    inserted = 0
    updated = 0
    skipped = 0
    
    with db.connect() as conn:
        for it in items:
            is_dup = it.get("_is_duplicate", False)
            if is_dup and not overwrite_duplicates:
                skipped += 1
                continue
            
            # Clean internal helper flags
            cleaned = {k: v for k, v in it.items() if not k.startswith("_")}
            
            # Calculate score safely
            serv_pts = (15 if cleaned.get("weg_management") == "Yes" else 0) + (15 if cleaned.get("rental_management") == "Yes" else 0) + (5 if cleaned.get("special_management") == "Yes" else 0)
            cnt_pts = 20 if cleaned.get("contact_person") and cleaned.get("email_type") == "personal_work" else 13 if cleaned.get("contact_person") else 8 if cleaned.get("contact_email") else 4 if cleaned.get("website") else 0
            u = cleaned.get("portfolio_units")
            u_pts = 25 if (u and u >= 5000) else 20 if (u and u >= 1500) else 15 if (u and u >= 500) else 10 if (u and u >= 100) else 5 if (u and u > 0) else 0
            m_pts = 10 if cleaned.get("metering_signal") == "High" else 5 if cleaned.get("metering_signal") == "Medium" else 0
            ev_pts = 5
            score = serv_pts + cnt_pts + u_pts + m_pts + ev_pts
            cleaned["score"] = score
            cleaned["tier"] = "Tier 1" if score >= 80 else "Tier 2" if score >= 60 else "Tier 3"
            cleaned["raw"] = {"imported": True, "score_breakdown": {"service_fit": serv_pts, "portfolio_scale": u_pts, "contact_quality": cnt_pts, "metering_signal": m_pts, "evidence_quality": ev_pts}}
            cleaned["evidence"] = []
            cleaned["sources"] = [{"url": cleaned.get("website") or "imported_source", "title": "Imported Record", "type": "user_import", "retrieved_at": db.now_iso()}] if cleaned.get("website") else []
            cleaned["gaps"] = []
            
            db.upsert_lead(cleaned)
            if is_dup:
                updated += 1
            else:
                inserted += 1

    return {"inserted": inserted, "updated": updated, "skipped": skipped, "total": len(items)}

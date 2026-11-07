from __future__ import annotations
import csv, io, json, threading, uuid
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, UploadFile, File, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from . import config, db
from .ollama import ollama_status, test_ollama_prompt, test_groq_prompt
from .ai_router import get_ai_status
from .research import run_research, cancel_job
from .export_xlsx import generate_leads_workbook
from .importer import preview_import, commit_import
from .auth import require_user, login as supabase_login
from .queue import enqueue, QueueUnavailable

app=FastAPI(title="Heidi Lead Intelligence Agent",version="1.0.0",description="Local-first, city-configurable B2B prospect research")
app.mount("/static",StaticFiles(directory=str(config.STATIC_PATH)),name="static")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def production_authentication(request, call_next):
    public = {"/api/health", "/api/auth/login", "/api/auth/config"}
    if config.IS_PRODUCTION and request.url.path.startswith("/api/") and request.url.path not in public:
        try:
            request.state.user = require_user(request)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return await call_next(request)


class ResearchRequest(BaseModel):
    city: str = Field(min_length=2,max_length=80)
    country: str = Field(min_length=2,max_length=80)
    max_companies: int = Field(default=12,ge=1,le=50)
    keywords: list[str] = Field(default_factory=list)
    use_local_model: bool = True

class SettingsPatch(BaseModel):
    ai_provider: str | None = Field(default=None, max_length=20)
    groq_model: str | None = Field(default=None, max_length=120)
    ollama_base_url: str | None = Field(default=None, max_length=240)
    ollama_model: str | None = Field(default=None, min_length=1, max_length=120)
    ai_fallback_enabled: bool | None = None

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)

class CommitImportRequest(BaseModel):
    items: list[dict]
    overwrite_duplicates: bool = False

class LeadPatch(BaseModel):
    status: str | None = None
    notes: str | None = None
    contact_person: str | None = None
    contact_role: str | None = None
    contact_email: str | None = None
    email_type: str | None = None
    phone: str | None = None
    portfolio_units: int | None = None
    portfolio_buildings: int | None = None
    vdiv_member: str | None = None


@app.on_event("startup")
def startup():
    db.init_db()
    # Persisted settings override .env after first launch.
    provider = db.get_setting("ai_provider", config.AI_PROVIDER)
    if provider in ("auto", "groq", "ollama"): config.AI_PROVIDER = provider
    groq_model = db.get_setting("groq_model", config.GROQ_MODEL)
    if groq_model: config.GROQ_MODEL = groq_model
    fallback_en = db.get_setting("ai_fallback_enabled", str(config.AI_FALLBACK_ENABLED))
    config.AI_FALLBACK_ENABLED = fallback_en.lower() in ("true", "1", "yes")

    base = db.get_setting("ollama_base_url", config.OLLAMA_BASE_URL)
    model = db.get_setting("ollama_model", config.OLLAMA_MODEL)
    if _is_local_url(base): config.OLLAMA_BASE_URL = base.rstrip("/")
    if model: config.OLLAMA_MODEL = model


def _is_local_url(url: str) -> bool:
    try:
        p=urlparse(url)
        return p.scheme in ("http","https") and p.hostname in ("127.0.0.1","localhost","::1") and not p.username and not p.password
    except Exception: return False


@app.get("/")
def index():
    return FileResponse(config.STATIC_PATH/"index.html")

@app.get("/api/health")
def health():
    ai = get_ai_status()
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        database_status = "connected"
    except Exception:
        database_status = "unavailable"
    queue_status = "configured" if config.REDIS_URL and config.REDIS_TOKEN else "not_configured"
    overall = "ok" if database_status == "connected" and (not config.IS_PRODUCTION or queue_status == "configured") else "degraded"
    seeded = len(db.list_leads(city="Berlin",country="Germany",limit=2000)) if database_status == "connected" else 0
    return {"status":overall,"version":app.version,"database":database_status,"queue":queue_status,"ai":ai,"ollama":ai["ollama"],
        "search_provider":"Serper" if config.SERPER_API_KEY else "DDGS metasearch",
        "seeded_berlin_leads":seeded}

@app.get("/api/auth/config")
def auth_config():
    return {"required": config.IS_PRODUCTION, "supabase_url": config.SUPABASE_URL, "supabase_anon_key": config.SUPABASE_ANON_KEY}

@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    return supabase_login(req.email, req.password)

@app.get("/api/auth/me")
def auth_me(request: Request):
    return require_user(request)

@app.get("/api/settings")
def settings():
    ai = get_ai_status()
    return {
        "ai_provider": config.AI_PROVIDER,
        "ai_fallback_enabled": config.AI_FALLBACK_ENABLED,
        "groq_model": config.GROQ_MODEL,
        "ollama_base_url": config.OLLAMA_BASE_URL,
        "ollama_model": config.OLLAMA_MODEL,
        "ai": ai,
        "ollama": ai["ollama"],
        "search_provider": "Serper API" if config.SERPER_API_KEY else "DDGS metasearch",
        "max_pages_per_company": config.MAX_PAGES_PER_COMPANY,
        "default_city": "Berlin",
        "default_country": "Germany"
    }

@app.put("/api/settings")
def update_settings(req: SettingsPatch):
    if req.ai_provider is not None:
        p = req.ai_provider.strip().lower()
        if p in ("auto", "groq", "ollama"):
            config.AI_PROVIDER = p
            db.set_setting("ai_provider", p)
    if req.groq_model is not None:
        config.GROQ_MODEL = req.groq_model.strip()
        db.set_setting("groq_model", config.GROQ_MODEL)
    if req.ai_fallback_enabled is not None:
        config.AI_FALLBACK_ENABLED = req.ai_fallback_enabled
        db.set_setting("ai_fallback_enabled", str(req.ai_fallback_enabled))

    if req.ollama_base_url is not None:
        if not _is_local_url(req.ollama_base_url):
            raise HTTPException(400,"For local-only inference, Ollama URL must use localhost, 127.0.0.1 or ::1.")
        config.OLLAMA_BASE_URL=req.ollama_base_url.rstrip("/")
        db.set_setting("ollama_base_url",config.OLLAMA_BASE_URL)
    if req.ollama_model is not None:
        config.OLLAMA_MODEL=req.ollama_model.strip()
        db.set_setting("ollama_model",config.OLLAMA_MODEL)
    return settings()

@app.patch("/api/settings")
def patch_settings(req: SettingsPatch):
    return update_settings(req)

@app.get("/api/ai/status")
def ai_status_endpoint():
    return get_ai_status()

@app.post("/api/ai/test-groq")
def test_groq_endpoint():
    return test_groq_prompt()

@app.post("/api/ai/test-ollama")
def test_ollama_endpoint():
    return test_ollama_prompt()

@app.get("/api/ollama/models")
def models():
    return get_ai_status()["ollama"]

@app.post("/api/ollama/test")
def test_ollama():
    return test_ollama_prompt()

@app.post("/api/research")
def start_research(req: ResearchRequest):
    if not req.city.strip() or not req.country.strip(): raise HTTPException(400,"City and country are required")
    job_id=uuid.uuid4().hex[:12]
    db.create_job(job_id,req.city.strip(),req.country.strip(),req.max_companies)
    if config.IS_DEMO:
        if req.max_companies > 2:
            raise HTTPException(400, "Demo research is limited to 2 companies per request.")
        run_research(job_id, req.city.strip(), req.country.strip(), req.max_companies, req.keywords, False)
        return {"job_id": job_id, "status": db.get_job(job_id).get("status")}
    if config.IS_PRODUCTION:
        try:
            enqueue(job_id, req.city.strip(), req.country.strip(), req.max_companies, req.keywords, False)
        except QueueUnavailable as exc:
            db.update_job(job_id, status="failed", error=str(exc), finished_at=db.now_iso())
            raise HTTPException(503, str(exc))
    else:
        thread=threading.Thread(target=run_research,args=(job_id,req.city.strip(),req.country.strip(),req.max_companies,req.keywords,req.use_local_model),daemon=True)
        thread.start()
    return {"job_id":job_id,"status":"queued"}

@app.get("/api/jobs")
def jobs(city: str | None = None, country: str | None = None, limit: int = Query(20, ge=1, le=100)):
    return {"items": db.list_jobs(city, country, limit)}

@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    item=db.get_job(job_id)
    if not item: raise HTTPException(404,"Job not found")
    return item

@app.post("/api/jobs/{job_id}/cancel")
def cancel_research_job(job_id: str):
    item=db.get_job(job_id)
    if not item: raise HTTPException(404,"Job not found")
    success = cancel_job(job_id)
    return {"job_id": job_id, "cancelled": success, "status": db.get_job(job_id).get("status")}

@app.get("/api/leads")
def leads(city: str | None=None,country: str | None=None,q: str="",tier: str="",status: str="",limit: int=Query(500,ge=1,le=2000)):
    items=db.list_leads(city,country,q,tier,status,limit)
    return {"items":items,"count":len(items)}

@app.get("/api/leads/{lead_id}")
def lead(lead_id: str):
    item=db.get_lead(lead_id)
    if not item: raise HTTPException(404,"Lead not found")
    return item

@app.patch("/api/leads/{lead_id}")
def patch_lead(lead_id: str, patch: LeadPatch):
    if not db.get_lead(lead_id): raise HTTPException(404,"Lead not found")
    data=patch.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in ("New","Researching","Qualified","Contacted","Meeting","Not a fit","Seeded"):
        raise HTTPException(400,"Unsupported lead status")
    db.update_lead_fields(lead_id,data)
    return db.get_lead(lead_id)

@app.get("/api/cities")
def cities():
    return {"items":db.city_stats()}

@app.get("/api/export.csv")
def export_csv(city: str | None=None,country: str | None=None):
    items=db.list_leads(city,country,limit=2000)
    output=io.StringIO()
    columns=["id","city","country","name","website","address","weg_management","rental_management","special_management","portfolio_units","portfolio_buildings","contact_person","contact_role","contact_email","email_type","phone","metering_signal","score","tier","completeness","confidence","status","summary","rationale","gaps","sources"]
    writer=csv.DictWriter(output,fieldnames=columns,extrasaction="ignore")
    writer.writeheader()
    for x in items:
        row={k:x.get(k) for k in columns}
        row["gaps"]=" | ".join(x.get("gaps") or [])
        row["sources"]=" | ".join(s.get("url","") for s in x.get("sources",[]))
        writer.writerow(row)
    content="\ufeff"+output.getvalue()
    fname=f"heidi_leads_{(city or 'all').lower().replace(' ','_')}.csv"
    return StreamingResponse(iter([content]),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="{fname}"'})

@app.get("/api/export.json")
def export_json(city: str | None=None,country: str | None=None):
    items=db.list_leads(city,country,limit=2000)
    return items

@app.get("/api/export.xlsx")
def export_xlsx(city: str | None=None,country: str | None=None):
    leads_list = db.list_leads(city,country,limit=2000)
    # Collect associated runs if available
    with db.connect() as conn:
        runs_query = "SELECT * FROM jobs"
        params = []
        if city and country:
            runs_query += " WHERE city=? AND country=?"
            params = [city, country]
        elif city:
            runs_query += " WHERE city=?"
            params = [city]
        runs_query += " ORDER BY started_at DESC LIMIT 50"
        runs = [dict(r) for r in conn.execute(runs_query, params).fetchall()]

    buf = generate_leads_workbook(leads_list, runs)
    fname = f"heidi_leads_{(city or 'all').lower().replace(' ','_')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'}
    )

@app.post("/api/import/preview")
async def import_preview(
    file: UploadFile = File(...),
    city: str = Query("Berlin"),
    country: str = Query("Germany")
):
    try:
        content = await file.read()
        res = preview_import(content, file.filename or "import.csv", city, country)
        return res
    except Exception as exc:
        raise HTTPException(400, f"Failed to parse file: {str(exc)}")

@app.post("/api/import/commit")
def import_commit(req: CommitImportRequest):
    try:
        res = commit_import(req.items, req.overwrite_duplicates)
        return res
    except Exception as exc:
        raise HTTPException(400, f"Failed to commit import: {str(exc)}")

@app.get("/api/stats")
def stats(city: str | None=None,country: str | None=None):
    items=db.list_leads(city,country,limit=2000)
    return {"total":len(items),"tier1":sum(x["tier"]=="Tier 1" for x in items),
            "tier2":sum(x["tier"]=="Tier 2" for x in items),"named_contacts":sum(bool(x.get("contact_person")) for x in items),
            "emails":sum(bool(x.get("contact_email")) for x in items),"researched":sum(x.get("confidence") in ("High","Medium") for x in items),
            "cities":db.city_stats()}


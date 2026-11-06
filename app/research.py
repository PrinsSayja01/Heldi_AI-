from __future__ import annotations
import ipaddress, json, logging, re, socket, time, uuid
from collections import defaultdict
from urllib.parse import urlparse, urljoin, urldefrag
from urllib.robotparser import RobotFileParser
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from . import config, db
from .ollama import analyze_company

LOG = logging.getLogger("heidi.research")
USER_AGENT = "HeidiLeadResearchAgent/1.0 (local B2B research; respectful public-page retrieval)"
EMAIL_RE = re.compile(r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+")
PHONE_RE = re.compile(r"(?:\+?\d[\d ()/.-]{6,}\d)")
DIRECTORY_HOSTS = {
  "linkedin.com","facebook.com","instagram.com","youtube.com","x.com","wikipedia.org",
  "hausverwalter-register.de","vdiv-bb.de","immobilienscout24.de","immowelt.de",
  "gelbeseiten.de","11880.com","werkenntdenbesten.de","yelp.com","google.com",
  "maps.google.com","northdata.de","unternehmensregister.de","handelsregister.de",
    "meinestadt.de","dastelefonbuch.de","golocal.de","cylex.de","dasoertliche.de",
    "allpar.com","bestfrankfurt.com","companydata.com","iamexpat.de","microsoft.com",
    "msn.com","northdata.com","northdata.de","obsproject.com","prontopro.de",
    "visitberlin.de"
}


def _root_domain(host: str) -> str:
    host = (host or "").lower().split(":")[0].removeprefix("www.")
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in {"co","com","org","net","gov"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _is_public_http_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname: return False
        if p.username or p.password: return False
        host = p.hostname.lower()
        if host in ("localhost", "localhost.localdomain"): return False
        try:
            ips = socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)
            for item in ips:
                ip = ipaddress.ip_address(item[4][0])
                if not ip.is_global: return False
        except socket.gaierror:
            return False
        return True
    except Exception:
        return False


def build_queries(city: str, country: str, keywords: list[str] | None = None) -> list[str]:
    city, country = city.strip(), country.strip()
    if keywords:
        terms = [x.strip() for x in keywords if x.strip()]
    elif country.lower() in {"germany", "de", "deutschland"}:
        terms = ["Hausverwaltung", "WEG-Verwaltung", "Mietverwaltung", "Immobilienverwaltung"]
    else:
        terms = ["property management company", "residential property management", "building management", "rental property management"]
    return list(dict.fromkeys([f'"{term}" "{city}" "{country}"' for term in terms] + [f'"{city}" "{country}" property management']))


def _search_one(query: str, region: str, max_results: int) -> list[dict]:
    if config.SERPER_API_KEY:
        gl_map = {"de-de":"de","nl-nl":"nl","uk-en":"gb","us-en":"us","fr-fr":"fr","es-es":"es","it-it":"it","de-at":"at","de-ch":"ch"}
        payload = {"q": query, "num": max_results}
        if region in gl_map: payload["gl"] = gl_map[region]
        r = requests.post("https://google.serper.dev/search", headers={"X-API-KEY": config.SERPER_API_KEY, "Content-Type":"application/json"}, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        return [{"title":x.get("title",""),"url":x.get("link",""),"snippet":x.get("snippet","")} for x in data.get("organic",[]) if x.get("link")]
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError("DDGS is not installed. Run pip install -r requirements.txt or set SERPER_API_KEY in .env.") from exc
    results = DDGS(timeout=15).text(query, region=region, safesearch="moderate", max_results=max_results, backend="auto")
    return [{"title":x.get("title",""),"url":x.get("href",""),"snippet":x.get("body","")} for x in results if x.get("href")]


def discover(city: str, country: str, max_companies: int, keywords: list[str] | None = None, log=None) -> list[dict]:
    def say(m):
        if log: log(m)
        LOG.info(m)
    region_map = {"germany":"de-de","de":"de-de","deutschland":"de-de","netherlands":"nl-nl","the netherlands":"nl-nl","nl":"nl-nl","united kingdom":"uk-en","uk":"uk-en","great britain":"uk-en","united states":"us-en","usa":"us-en","us":"us-en","france":"fr-fr","spain":"es-es","italy":"it-it","austria":"de-at","switzerland":"de-ch"}
    region = region_map.get(country.lower(), "wt-wt")
    queries = build_queries(city,country,keywords)
    candidates: dict[str,dict] = {}
    say(f"Starting public-source discovery for {city}, {country}; {len(queries)} search queries")
    per_query = min(12, max(5, max_companies))
    errors=[]
    for i, query in enumerate(queries,1):
        say(f"Search {i}/{len(queries)}: {query}")
        try:
            results = _search_one(query, region, per_query)
            for item in results:
                url = urldefrag(item.get("url", ""))[0]
                if not _is_public_http_url(url): continue
                host = (urlparse(url).hostname or "").lower().removeprefix("www.")
                root = _root_domain(host)
                if any(host == h or host.endswith("."+h) for h in DIRECTORY_HOSTS): continue
                if root not in candidates:
                    candidates[root] = {"domain":root,"website":f"https://{root}","candidate_url":url,"search_title":item.get("title",""),"search_snippet":item.get("snippet",""),"search_sources":[]}
                candidates[root]["search_sources"].append({"url":url,"title":item.get("title",""),"snippet":item.get("snippet","")})
        except Exception as exc:
            errors.append(str(exc)[:180])
            say(f"Search source warning: {str(exc)[:160]}")
        time.sleep(0.35)
    found = list(candidates.values())[:max_companies]
    say(f"Discovery complete: {len(found)} distinct company domains found" + (f"; {len(errors)} query warnings" if errors else ""))
    return found


def _get_robots(host_url: str) -> RobotFileParser | None:
    try:
        p = urlparse(host_url)
        robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
        r = requests.get(robots_url, headers={"User-Agent":USER_AGENT}, timeout=4, allow_redirects=False)
        if r.status_code == 200:
            rp = RobotFileParser(); rp.set_url(robots_url); rp.parse(r.text.splitlines()); return rp
    except Exception:
        pass
    return None


def _extract_jsonld(soup: BeautifulSoup) -> list[dict]:
    out=[]
    for tag in soup.find_all("script", attrs={"type":"application/ld+json"}):
        try:
            raw=json.loads(tag.string or tag.get_text())
            nodes=raw if isinstance(raw,list) else [raw]
            for node in nodes:
                if isinstance(node,dict):
                    typ=node.get("@type")
                    if typ in ("Organization","LocalBusiness","RealEstateAgent","ProfessionalService","Person","Corporation") or isinstance(typ,list):
                        out.append(node)
        except Exception:
            continue
    return out[:10]


def crawl_company(candidate: dict, max_pages: int | None = None, log=None) -> list[dict]:
    max_pages = max_pages or config.MAX_PAGES_PER_COMPANY
    start = candidate.get("candidate_url") or candidate.get("website")
    host = urlparse(start).netloc
    root = f"{urlparse(start).scheme}://{host}"
    if not _is_public_http_url(start) or not _is_public_http_url(root): return []
    rp = _get_robots(root)
    queue=[start, root]
    visited=set(); pages=[]
    session=requests.Session()
    session.headers.update({"User-Agent":USER_AGENT,"Accept":"text/html,application/xhtml+xml"})
    while queue and len(pages)<max_pages:
        url=urldefrag(queue.pop(0))[0]
        if url in visited: continue
        visited.add(url)
        pu=urlparse(url)
        if pu.netloc.lower()!=urlparse(root).netloc.lower(): continue
        if not _is_public_http_url(url): continue
        if rp and not rp.can_fetch(USER_AGENT,url): continue
        try:
            # Follow only same-site redirects after checking the redirect target is public.
            request_url = url
            r = None
            for _redirect in range(4):
                r = session.get(request_url,timeout=config.REQUEST_TIMEOUT_SECONDS,allow_redirects=False,stream=True)
                if r.status_code in (301,302,303,307,308) and r.headers.get("location"):
                    target = urljoin(request_url, r.headers["location"])
                    if not _is_public_http_url(target) or _root_domain(urlparse(target).hostname or "") != _root_domain(urlparse(root).hostname or ""):
                        r.close(); r = None; break
                    request_url = target
                    r.close()
                    continue
                break
            if r is None: continue
            ctype=r.headers.get("content-type","").lower()
            if r.status_code>=400 or "text/html" not in ctype: r.close(); continue
            body=next(r.iter_content(chunk_size=1_500_000),b"")
            r.close()
            if len(body)>1_500_000: body=body[:1_500_000]
            encoding=r.encoding or "utf-8"
            html=body.decode(encoding,errors="ignore")
            soup=BeautifulSoup(html,"html.parser")
            for el in soup(["script","style","noscript","svg","iframe"]): el.decompose()
            title=soup.title.get_text(" ",strip=True) if soup.title else ""
            text=re.sub(r"\s+"," ",soup.get_text(" ",strip=True)).strip()[:9000]
            page_url = request_url
            # Preserve structured business data as a separate extract for the local model.
            jsonld=_extract_jsonld(BeautifulSoup(html,"html.parser"))
            jsonld_text=json.dumps(jsonld,ensure_ascii=False)[:3500]
            emails=list(dict.fromkeys([e.lower() for e in EMAIL_RE.findall(html+" "+text)]))
            phones=list(dict.fromkeys(PHONE_RE.findall(text)))[:5]
            page={"url":page_url,"title":title,"text":text,"jsonld":jsonld_text,"emails":emails,"phones":phones,"retrieved_at":db.now_iso()}
            pages.append(page)
            # Find only relevant same-site pages. No broad crawling.
            if len(pages)<max_pages:
                links=[]
                for a in soup.find_all("a",href=True):
                    href=urljoin(page_url,a["href"])
                    hp=urlparse(href)
                    if hp.netloc.lower()!=urlparse(root).netloc.lower() or hp.scheme not in ("http","https"): continue
                    path=(hp.path+" "+a.get_text(" ",strip=True)).lower()
                    if any(k in path for k in ("kontakt","contact","impressum","team","unternehmen","about","ueber","geschäftsführung","geschaeftsfuehrung","verwaltung","leistungen","service","portfolio")):
                        clean=urldefrag(href)[0]
                        if clean not in visited and clean not in queue: links.append(clean)
                queue.extend(links[:max_pages])
            time.sleep(config.CRAWL_DELAY_SECONDS)
        except requests.RequestException:
            continue
    return pages


def fallback_analysis(candidate: dict, pages: list[dict]) -> dict:
    text=" ".join(p.get("text","") for p in pages).lower()
    combined=" ".join(p.get("text","") for p in pages)
    def flag(patterns): return "Yes" if any(re.search(p,text,re.I) for p in patterns) else "Unknown"
    weg=flag([r"\bweg[- ]?verwaltung\b",r"wohnungseigent[uü]mergemeinschaft",r"wohnungseigentumsverwaltung"])
    rental=flag([r"\bmietverwaltung\b",r"mietmanagement",r"rental management"])
    special=flag([r"sondereigentumsverwaltung",r"sondereigentum"])
    units=None
    m=re.search(r"\b([\d.]{2,8})\s*(?:wohneinheiten|einheiten|wohnungen|apartments|units|objekte)\b",text,re.I)
    if m:
        try: units=int(m.group(1).replace(".",""))
        except ValueError: pass
    all_emails=list(dict.fromkeys(e for p in pages for e in p.get("emails",[])))
    generic_prefixes={"info","kontakt","office","service","verwaltung","post","mail","hello","support","buchhaltung","team"}
    email=next((e for e in all_emails if e.split("@")[0].split("+")[0].lower() not in generic_prefixes),None)
    if not email: email=next(iter(all_emails),None)
    email_type="generic" if email and email.split("@")[0].split("+",1)[0].lower() in generic_prefixes else "unknown" if email else None
    signal="High" if any(k in text for k in ("fernablesung","funkablesung","heizkostenverteiler","wärmemengenzähler","messdienstleister","hkvo")) else "Medium" if any(k in text for k in ("heizkosten","warmwasserzähler","verbrauchserfassung")) else "Unknown"
    evidence=[]
    for p in pages:
        for key, pat in [("WEG management",r"weg[- ]?verwaltung"),("Rental management",r"mietverwaltung"),("Metering signal",r"fernablesung|heizkosten|messdienst")]:
            hit=re.search(pat,p.get("text",""),re.I)
            if hit:
                excerpt=p["text"][max(0,hit.start()-90):min(len(p["text"]),hit.end()+180)]
                evidence.append({"field":key,"value":"Keyword evidence","quote":excerpt,"source_url":p["url"]})
    return {
      "company_name":candidate.get("search_title") or candidate.get("domain"),"address":None,
      "weg_management":weg,"rental_management":rental,"special_management":special,
      "portfolio_units":units,"portfolio_buildings":None,"digital_portal":"Unknown","vdiv_member":"Unknown",
      "metering_signal":signal,"summary":"Public website content was retrieved; local model analysis was not available, so this is a rules-based preliminary extraction.",
      "rationale":"Property-management service keywords were found on the public website. Confirm actual residential portfolio and purchasing authority.",
      "contacts":[{"name":None,"role":None,"email":email,"email_type":email_type,"source_url":next((p["url"] for p in pages if email and email in p.get("emails",[])),None)}] if email else [],
      "evidence":evidence,"gaps":["Local Ollama analysis did not run; review the extracted facts.","Confirm managed units and buildings.","Confirm who selects metering providers.","Confirm existing meter technology and incumbent supplier."]
    }


def calculate_score(a: dict, pages: list[dict]) -> dict:
    weg=a.get("weg_management","Unknown")=="Yes"
    rental=a.get("rental_management","Unknown")=="Yes"
    special=a.get("special_management","Unknown")=="Yes"
    service=min(35,(15 if weg else 0)+(15 if rental else 0)+(5 if special else 0))
    units=a.get("portfolio_units")
    scale=0
    if isinstance(units,int):
        scale=5 if units<100 else 10 if units<500 else 15 if units<1500 else 20 if units<5000 else 25
    contacts=a.get("contacts") or []
    named=next((c for c in contacts if c.get("name")),None)
    email_contact=next((c for c in contacts if c.get("email")),None)
    if named and named.get("email") and named.get("email_type")=="personal_work": contact_score=20
    elif named: contact_score=13
    elif email_contact and email_contact.get("email_type")=="generic": contact_score=8
    elif email_contact: contact_score=10
    elif pages: contact_score=4
    else: contact_score=0
    signal=str(a.get("metering_signal","Unknown")).lower()
    modern=10 if signal=="high" else 7 if signal=="medium" else 4 if signal=="low" else 0
    evidence_count=len(a.get("evidence") or [])
    evidence_score=(4 if pages else 0)+(3 if len(pages)>1 else 0)+(3 if evidence_count>=2 else 1 if evidence_count==1 else 0)
    score=service+scale+contact_score+modern+evidence_score
    weighted_known = [
      (bool(a.get("address")),1), (bool(pages),1),
      (a.get("weg_management") not in (None,"Unknown"),1),
      (a.get("rental_management") not in (None,"Unknown"),1),
      (a.get("special_management") not in (None,"Unknown"),1),
      (units is not None,2), (a.get("portfolio_buildings") is not None,1),
      (bool(named),1), (bool(email_contact),1),
      (any(p.get("phones") for p in pages),1),
      (a.get("digital_portal") not in (None,"Unknown"),1),
      (a.get("vdiv_member") not in (None,"Unknown"),1),
      (signal!="unknown",2), (evidence_count>=2,2)
    ]
    completeness=round(sum(weight for present,weight in weighted_known if present)/sum(weight for _,weight in weighted_known)*100)
    confidence="High" if len(pages)>=3 and evidence_count>=3 else "Medium" if pages else "Low"
    tier="Tier 1" if score>=80 else "Tier 2" if score>=60 else "Tier 3"
    return {"score":score,"tier":tier,"completeness":completeness,"confidence":confidence,
      "score_breakdown":{"service_fit":service,"portfolio_scale":scale,"contact_quality":contact_score,"metering_signal":modern,"evidence_quality":evidence_score}}


def _company_payload(candidate: dict, city: str, country: str, pages: list[dict], analysis: dict) -> dict:
    contact = max((c for c in analysis.get("contacts",[]) if c.get("name") or c.get("email")), key=lambda c: (5 if c.get("name") and c.get("email_type")=="personal_work" else 4 if c.get("name") else 3 if c.get("email") and c.get("email_type")=="unknown" else 2 if c.get("email") else 0), default={})
    score=calculate_score(analysis,pages)
    sources=[]
    for p in pages:
        sources.append({"url":p["url"],"title":p.get("title",""),"type":"company_website","snippet":p.get("text","")[:340],"retrieved_at":p.get("retrieved_at")})
    for s in candidate.get("search_sources",[]):
        sources.append({"url":s["url"],"title":s.get("title",""),"type":"search_result","snippet":s.get("snippet",""),"retrieved_at":db.now_iso()})
    source_urls={s["url"] for s in sources}
    # Do not persist inferred or unverified contact details.
    return {
      "city":city,"country":country,"name":analysis.get("company_name") or candidate.get("search_title") or candidate.get("domain"),
      "website":candidate.get("website"),"domain":candidate.get("domain"),"address":analysis.get("address"),
      "weg_management":analysis.get("weg_management","Unknown"),"rental_management":analysis.get("rental_management","Unknown"),
      "special_management":analysis.get("special_management","Unknown"),"portfolio_units":analysis.get("portfolio_units"),
      "portfolio_buildings":analysis.get("portfolio_buildings"),"digital_portal":analysis.get("digital_portal","Unknown"),
      "vdiv_member":analysis.get("vdiv_member","Unknown"),"contact_person":contact.get("name"),"contact_role":contact.get("role"),
      "contact_email":contact.get("email"),"email_type":contact.get("email_type"),"phone":next((pno for p in pages for pno in p.get("phones",[])),None),
      "service_evidence_status":"Public company website reviewed" if pages else "Search results only; website could not be reviewed",
      "metering_signal":analysis.get("metering_signal","Unknown"),"summary":analysis.get("summary"),"rationale":analysis.get("rationale"),
      **score,"evidence":[e for e in analysis.get("evidence",[]) if e.get("source_url") in source_urls],
      "gaps":analysis.get("gaps",[]),"sources":sources,"raw":{"search_candidate":candidate,"model_analysis":analysis,"pages_retrieved":len(pages),"score_breakdown":score.get("score_breakdown",{})}
    }


# Job cancellation registry
CANCELLED_JOBS = set()


def cancel_job(job_id: str) -> bool:
    """Signals a running background job to cancel gracefully."""
    CANCELLED_JOBS.add(job_id)
    job = db.get_job(job_id)
    if job and job.get("status") in ("queued", "running"):
        db.update_job(job_id, status="cancelling", current_step="Cancellation requested by user")
        return True
    return False


def is_job_cancelled(job_id: str) -> bool:
    return job_id in CANCELLED_JOBS


def run_research(job_id: str, city: str, country: str, max_companies: int, keywords: list[str] | None, use_local_model: bool=True) -> None:
    logs=[]
    def log(message: str):
        logs.append({"at":datetime.now(timezone.utc).strftime("%H:%M:%S"),"message":message})
        logs[:] = logs[-80:]
        db.update_job(job_id,logs_json=logs,current_step=message)
    try:
        if is_job_cancelled(job_id):
            db.update_job(job_id, status="cancelled", current_step="Job cancelled before discovery", finished_at=db.now_iso(), logs_json=logs)
            return

        db.update_job(job_id,status="running",progress=2,current_step="Discovering companies")
        candidates=discover(city,country,max_companies,keywords,log)
        
        if is_job_cancelled(job_id):
            db.update_job(job_id, status="cancelled", current_step="Job cancelled after discovery", finished_at=db.now_iso(), logs_json=logs)
            return

        db.update_job(job_id,total=len(candidates),progress=12)
        if not candidates:
            log("No company domains were discovered. Try alternate local search terms or configure SERPER_API_KEY.")
        saved=0
        for i,candidate in enumerate(candidates,1):
            if is_job_cancelled(job_id):
                log(f"Job cancelled by user at candidate [{i}/{len(candidates)}]. Preserving already saved records.")
                db.update_job(job_id, status="cancelled", progress=12+int((i/max(len(candidates),1))*85), found=saved, processed=i-1, current_step="Cancelled by user", finished_at=db.now_iso(), logs_json=logs)
                return

            log(f"[{i}/{len(candidates)}] Reviewing {candidate.get('domain')}")
            pages=crawl_company(candidate)
            if not pages:
                log(f"Could not retrieve a permitted public website for {candidate.get('domain')}; retaining as an unverified prospect.")
            analysis=None
            if use_local_model and pages:
                try:
                    analysis=analyze_company(candidate.get("search_title","Unknown"),city,country,pages,candidate.get("search_sources",[]))
                    provider_used = analysis.get("_ai_provider_used", "AI")
                    model_used = analysis.get("_ai_model_used", "")
                    log(f"AI extraction completed for {candidate.get('domain')} via {provider_used.upper()} ({model_used})")
                except Exception as exc:
                    log(f"AI analysis unavailable for {candidate.get('domain')}: {str(exc)[:120]}; using rules-based extraction")
            if not analysis:
                analysis=fallback_analysis(candidate,pages)
            payload=_company_payload(candidate,city,country,pages,analysis)
            db.upsert_lead(payload)
            saved+=1
            progress=12+int((i/max(len(candidates),1))*85)
            db.update_job(job_id,progress=progress,found=saved,processed=i)

        if is_job_cancelled(job_id):
            db.update_job(job_id, status="cancelled", progress=100, found=saved, processed=len(candidates), current_step="Cancelled by user", finished_at=db.now_iso(), logs_json=logs)
        else:
            db.update_job(job_id,status="completed",progress=100,found=saved,processed=len(candidates),current_step="Research completed",finished_at=db.now_iso(),logs_json=logs)
    except Exception as exc:
        LOG.exception("Research job failed")
        log(f"Research stopped: {str(exc)[:300]}")
        db.update_job(job_id,status="failed",error=str(exc)[:500],finished_at=db.now_iso(),logs_json=logs)
    finally:
        CANCELLED_JOBS.discard(job_id)

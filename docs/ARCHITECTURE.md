# Architecture & Data Flow: Heidi Lead Intelligence Agent

## Overview
Heidi Lead Intelligence Agent is a local-first B2B prospect research and lead qualification application designed specifically for Heidi Systems' metering, submetering, and heating-cost billing business.

The system discovers property managers (`Hausverwaltungen`), retrieves public company website data, extracts factual business information using an on-device local Ollama model, validates claims directly against the retrieved text, and computes an explainable 100-point qualification score.

```
+-------------------------------------------------------------------------+
|                           User Browser UI                               |
|        (Vanilla HTML5 / Modern CSS / Reactive JavaScript Client)        |
+-------------------------------------------------------------------------+
                                    |
                         REST API (HTTP / JSON)
                                    v
+-------------------------------------------------------------------------+
|                       FastAPI Application Server                        |
|                         (Bound to 127.0.0.1:8787)                       |
|                                                                         |
|  - Health & Settings Controller    - Export Controller (CSV, JSON, XLSX)|
|  - Leads & CRM Controller          - Import Controller (Preview/Commit) |
|  - Research Background Jobs        - Job Cancellation Registry          |
+-------------------------------------------------------------------------+
       |                           |                          |
       v                           v                          v
+--------------+          +-------------------+     +---------------------+
| SQLite (WAL) |          |  Research Engine  |     | Local Ollama Engine |
| data/heidi_  |          |                   |     | (127.0.0.1:11434)   |
| leads.db     |          | - Search Adapter  |     |                     |
+--------------+          |   (Serper / DDGS) |     | - Tag Discovery     |
                          | - Robots Parser   |     | - JSON Chat Schema  |
                          | - SSRF Validator  |     | - Repair Retries    |
                          | - HTML / JSON-LD  |     | - Strict Validation |
                          +-------------------+     +---------------------+
```

---

## Component Details

### 1. Web Frontend (`static/`)
- **Single-page interface** built with vanilla HTML/CSS/JavaScript with responsive layout for desktop and mobile.
- **Overview Dashboard**: Pipeline snapshot metrics, high-priority prospects, tier distribution, and local model connection status.
- **Lead Explorer**: Search, multi-criteria filtering (city, tier, status, service categories, contact availability), inline editing, and multi-format exports.
- **New Research**: City and country parameters, localized keyword definitions, search provider indicators, crawl settings, real-time background job progress bar, cancel button, and streaming log box.
- **Model & Settings**: Local Ollama model discovery, model selection, live connection test, and prompt test.
- **Lead Drawer**: Granular dimension-by-dimension score explanations, verified evidence quotations linked to source URLs, research gaps, source citations, and editable sales notes.
- **Import Modal**: CSV and JSON drag-and-drop preview, duplicate collision detection against current market, and selective commit.

### 2. Backend Server (`app/main.py`)
- **FastAPI** application configured to bind strictly to `127.0.0.1` by default.
- Implements endpoints:
  - `GET /api/health`
  - `GET /api/leads`
  - `GET /api/leads/{lead_id}`
  - `PATCH /api/leads/{lead_id}`
  - `GET /api/stats`
  - `POST /api/research`
  - `GET /api/jobs/{job_id}`
  - `POST /api/jobs/{job_id}/cancel`
  - `GET /api/export.csv`
  - `GET /api/export.json`
  - `GET /api/export.xlsx`
  - `POST /api/import/preview`
  - `POST /api/import/commit`
  - `GET /api/settings`
  - `PUT /api/settings` and `PATCH /api/settings`
  - `GET /api/ollama/models`
  - `POST /api/ollama/test`

### 3. Multi-Step Research Engine (`app/research.py`)
1. **Query Construction**: Builds local-language search queries adapted to city and country (e.g., German terms for Germany/Austria/Switzerland; English for other international markets).
2. **Public Discovery**: Searches via Serper API (when `SERPER_API_KEY` is provided) or DDGS metasearch fallback. Filters directory and social hosts (LinkedIn, Yelp, Facebook, GelbeSeiten).
3. **SSRF Guard**: Validates destination URLs against localhost, private IP subnets, loopback, link-local, and reserved ranges before initiating requests.
4. **Polite Crawling**: Respects `robots.txt`, enforces polite delays, strict timeouts, same-host scope, and maximum page limits.
5. **Information Extraction**: Combines page text and JSON-LD schema into untrusted context for extraction.

### 4. Local AI & Deterministic Fallback (`app/ollama.py`)
- Interacts strictly with Ollama's local HTTP API (`http://127.0.0.1:11434`).
- Implements prompt repair: if initial model output has a syntax error, issues a repair prompt with low temperature.
- **Strict Verification Against Ground Truth**:
  - Email addresses must exactly match strings physically present in fetched pages.
  - Named persons, roles, phone numbers, addresses, and portfolio unit numbers must exist in the retrieved text.
  - Service categories are marked `Unknown` if not backed by explicit textual patterns.
  - Absence of a signal on a website is always treated as `Unknown`, never assumed `No`.
- **Offline Fallback**: When Ollama is offline or uninstalled, the engine executes deterministic regex-based rules and labels records as `Rules-based extraction`.

### 5. Deterministic Qualification Engine
- 100-point explainable rubric:
  - **Service Fit (35 pts)**: WEG management (15), Rental management (15), SEV (5).
  - **Portfolio Scale (25 pts)**: Publicly disclosed units (<100: 5, 100-499: 10, 500-1,499: 15, 1,500-4,999: 20, 5,000+: 25).
  - **Contact Quality (20 pts)**: Named person + direct business email (20), Named person (13), Generic business inbox (8), Contact route (4).
  - **Metering Signal (10 pts)**: Remote reading, heat cost allocators, submetering, HKVO.
  - **Evidence Quality (10 pts)**: Official domain retrieved, multiple pages verified, verbatim quotes.

### 6. Export & Import Engine (`app/export_xlsx.py`, `app/importer.py`)
- **Excel (.xlsx)**: 5 styled tabs (`Leads`, `Evidence`, `Scoring`, `Research Runs`, `Read Me`) with frozen header rows, auto-filtered tables, right-aligned numeric data, and full rubric documentation.
- **CSV & JSON**: Standard UTF-8 encoded exports.
- **Importer**: Multi-format column normalizer, duplicate detection against existing SQLite records, preview modal, and transaction-safe commitment.

## Production Deployment

Vercel serves the static frontend and `/api/config.js` only. The FastAPI API and research worker run on a persistent backend host using `render.yaml`; they must not run as Vercel background threads.

- **Database:** local SQLite remains available for development/tests. Production uses `DATABASE_URL` with Supabase Postgres through `app/postgres.py`.
- **Authentication:** Supabase Auth issues bearer JWTs. Production API routes require a verified JWT; health, login and configuration discovery are public.
- **Queue:** `app/queue.py` enqueues research requests in Upstash Redis. `app/worker.py` consumes jobs and calls the existing research engine with retry/error persistence.
- **AI:** production uses GroqCloud server-side. Local Ollama is disabled in production and remains a development fallback only.
- **CORS:** production origins are explicit through `CORS_ORIGINS`; wildcard credentialed CORS is not used.
- **Migration:** seed/import migration must run against the managed database before enabling production traffic. The local SQLite file is never used as production state.

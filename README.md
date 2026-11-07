# Heidi Lead Intelligence Agent

A local-first B2B prospect research application built for the Heidi Systems Hausverwaltung case study. It starts with the 142 Berlin prospects from the accompanying 06 Nov 2026 workbook and can run fresh research for any city and country.

## What it does

- **City-configurable discovery:** enter a city, country, service category, local search terms and a research limit. Berlin is the starting market, not a hard-coded constraint.
- **Public web discovery:** searches for relevant company domains using DDGS metasearch by default. Set `SERPER_API_KEY` in `.env` to use Serper instead.
- **Respectful enrichment:** checks company-owned websites, reads relevant contact, imprint, team and service pages, and honours the site's `robots.txt` rules when available. It does not scrape LinkedIn.
- **Provider-routed AI extraction:** uses GroqCloud (`openai/gpt-oss-120b`) when configured and automatically falls back to local Ollama on `127.0.0.1` for rate limits, quota errors, authentication failures, timeouts or network failures. The model extracts WEG / rental / special-property management, disclosed portfolio size, public business contacts, metering signals, citations and qualification gaps.
- **Evidence validation:** model-suggested email addresses must match an address actually found in the fetched page. Service flags, portfolio numbers, membership and evidence excerpts are checked against the source text. Unsupported fields stay `Unknown` or blank.
- **Explainable qualification:** a deterministic 100-point score covers service fit (35), portfolio scale (25), contact quality (20), metering signals (10) and evidence quality (10).
- **Local CRM:** saves prospects, sources, notes and sales status to SQLite. Leads remain separated by city and country.
- **Exports:** 5-tab Excel (.xlsx) workbook, CSV and JSON exports.
- **Import:** CSV and JSON dataset importer with duplicate detection and preview.
- **Job Control:** real-time background research progress, streaming log inspection, and safe job cancellation.

## Product architecture

```text
Browser UI (vanilla JS)
        |
        v
FastAPI local server (127.0.0.1:8787)
        |
        +---- DDGS / optional Serper search ---- public search results
        |
        +---- bounded company-site crawler ---- HTML, contact pages, JSON-LD
        |
        +---- Ollama local API --------------- Qwen / other installed local model
        |
        +---- source validation + scoring ---- evidence, gaps, score, tier
        |
        +---- SQLite ------------------------- city-scoped lead database
        |
        +---- CSV / JSON export
```

## Run on macOS (Apple Silicon)

The app is designed for a local Mac setup. GroqCloud is the configured primary AI provider and Ollama is the local fallback. API keys stay in the backend environment and are never sent to the browser. Set `AI_PROVIDER=ollama` to keep all inference local.

1. Install [Ollama](https://ollama.com/download/mac) and open it.
2. In Terminal, move to this project folder.
3. Run:

   ```bash
   chmod +x start_mac.sh
   ./start_mac.sh
   ```

4. Open `http://127.0.0.1:8787` in your browser.
5. In **Model & settings**, select a model that appears in your local Ollama model list.

The default model is `qwen2.5:0.5b`, a lightweight model that works reliably on an 8 GB Apple Silicon machine. To install it if needed:

```bash
ollama pull qwen2.5:0.5b
```

If you already have `qwen3:8b`, `qwen2.5:3b`, `gemma3:1b` or another Ollama model installed, select it in **Model & settings**. The app discovers installed model names from your local Ollama service.

### Manual run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
ollama serve                 # in a separate terminal, if Ollama is not already running
ollama pull qwen2.5:0.5b    # optional if using a model already installed
uvicorn app.main:app --host 127.0.0.1 --port 8787
```

## Run on Windows

Use `start_windows.bat`. It creates the virtual environment, installs requirements, and starts the app. Install Ollama separately and choose an installed model in the settings page. On macOS, you can also double-click `start_mac.command` after allowing Terminal to open it.

## First launch

- The database is created at `data/heidi_leads.db`.
- The 142 Berlin prospects are imported from `data/berlin_seed.json` once, only if Berlin has no existing records.
- Existing seed records are labelled `Seeded` and retain the original source URLs and research notes. They are not silently represented as newly verified.
- A new research run for another city stores that market separately. The last selected city is remembered in that browser.

## Research workflow

1. Open **New research**.
2. Enter the target city and country. Change the keywords to local terms where needed.
3. Choose the number of company domains to examine.
4. Keep **Use local AI enrichment** enabled to analyse company pages through Ollama.
5. Start the run. Discovery, retrieval, extraction, validation and scoring happen as a background job.
6. Open each lead to inspect facts, source URLs, excerpts and missing data.
7. Update status / internal notes and export the current city to CSV.

## Search providers and licensing

The default search integration is the `ddgs` Python metasearch package. Search is external because current public websites must be discovered. The package's published notice describes it as intended for educational use. For ongoing commercial prospecting, configure a search provider whose terms explicitly permit your use case, such as Serper, by putting the key in `.env`:

```env
SERPER_API_KEY=your_key_here
```

Restart the app after editing `.env`. This API key is never sent to Ollama. Do not commit `.env`.

## Local model and privacy

- The browser UI and database run on `127.0.0.1` only by default.
- The Ollama base URL is restricted in the settings UI to localhost addresses.
- Company search queries and HTTP page requests still leave your computer because fresh public-source research requires internet access.
- Retrieved page text is sent to the selected AI provider. In `auto` mode, GroqCloud is attempted first and Ollama is used automatically when Groq is unavailable; set `AI_PROVIDER=ollama` for local-only inference.
- The app stores public business contact information locally. Use it only with an appropriate legal basis and follow applicable privacy and direct-marketing rules. A publicly visible email address is not automatic consent to marketing.

## Important data limitations

- Search engines do not return every company. A research run is a discoverable sample, not a complete registry of every property manager in a city.
- Some websites block automated requests, publish little detail, or do not expose their management portfolio.
- A missing signal is `Unknown`, not `No`.
- A score is a research prioritisation aid. It is not proof of purchasing intent, a current metering problem, or a verified need for Heidi Systems.
- Personal / professional contact emails are kept only when present in a retrieved public source. The app does not generate email patterns or scrape personal LinkedIn pages.
- A person, role or phone number must be checked before outreach. Manual human review remains required.

## Tests

```bash
pytest -q
```

## Vercel Demo Deployment

The public demo is a single Vercel project. Root `index.py` exposes the existing FastAPI app, and Vercel serves the frontend and API on the same origin. Set `ENVIRONMENT=demo`, use `/tmp/companyatlas-demo.db`, and bundle `data/demo_seed.json`; no external database, queue, auth service, or second host is required. `/tmp` is temporary and resets on a cold start, so this is not persistent cloud storage.

Groq is optional for the demo. When `GROQ_API_KEY` is unavailable or rate-limited, the existing deterministic rules-based extraction preserves retrieved facts without inventing AI output. Demo research is synchronous and limited to two companies per request to fit the serverless function duration.

The managed Postgres/Auth/queue code and `render.yaml` remain as a future secured deployment option, but they are not required by `ENVIRONMENT=demo`.

## API quick reference

- `GET /api/health` - Ollama, search provider and database health
- `GET /api/leads?city=Berlin&country=Germany` - lead list with filters
- `GET /api/leads/{lead_id}` - full lead profile with evidence and gaps
- `PATCH /api/leads/{lead_id}` - update contact, status, units, notes
- `GET /api/stats?city=Berlin&country=Germany` - dashboard metrics
- `POST /api/research` - start a city scan
- `GET /api/jobs/{job_id}` - research progress and logs
- `POST /api/jobs/{job_id}/cancel` - safely cancel running research
- `GET /api/export.xlsx?city=Berlin&country=Germany` - 5-tab Excel workbook
- `GET /api/export.csv?city=Berlin&country=Germany` - Excel-friendly CSV
- `GET /api/export.json?city=Berlin&country=Germany` - full structured data
- `POST /api/import/preview` - preview uploaded CSV/JSON and detect duplicates
- `POST /api/import/commit` - save verified imported records
- `GET /api/settings` - get local runtime and search settings
- `PATCH /api/settings` - update model or loopback endpoint
- `GET /api/ollama/models` - discover installed local models
- `POST /api/ollama/test` - run inference test prompt on local model
- `GET /docs` - local Swagger UI

## Folder structure

```text
app/                FastAPI, SQLite, Ollama, discovery, crawling and scoring
static/             Responsive dashboard UI
 data/berlin_seed.json  Original 142-lead Berlin case-study seed
 data/heidi_leads.db    Created on first launch
 docs/               Product and research design notes
tests/               Unit tests
```

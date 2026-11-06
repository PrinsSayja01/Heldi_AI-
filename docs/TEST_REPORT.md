# Heidi Lead Intelligence Agent — Verification & Test Report

**Execution Date:** 06 November 2026  
**Environment:** macOS (Apple Silicon), Python 3.12.8, Pytest 8.4.2  
**Database:** SQLite 3 (WAL Mode, Foreign Keys ON)  
**Baseline Seed Dataset:** 142 Berlin Property Management Leads (`data/berlin_seed.json`)  

---

## 1. Automated Test Suite Results

### Final verification (06 November 2026)

- **Command:** `pytest -q`
- **Result:** 30 passed, 0 failed, 2 FastAPI deprecation warnings.
- The earlier 19-test count in this document is stale.
- Live provider checks: Groq succeeded with `openai/gpt-oss-120b`; Ollama succeeded with `qwen2.5:0.5b`.
- A live Groq `HTTP 429` was observed during research and recorded as a GroqCloud rate-limit/quota event; the router automatically used Ollama. The unrelated earlier “Individual quota reached” message cannot be attributed to Antigravity from repository evidence.
- Controlled live research: Berlin requested 10 and saved 6 distinct domains; Frankfurt requested 10 and saved 10. Existing market totals after the runs are 152 Berlin and 11 Frankfurt records.
- Current records with at least one official company-website source: Berlin 7; Frankfurt 8.
- Live workbook validation: five sheets (`Leads`, `Evidence`, `Scoring`, `Research Runs`, `Read Me`), populated rows, filters, and frozen headers.
- Live browser validation: dashboard, lead explorer, company detail drawer, settings, provider tests, and persisted research activity rendered over HTTP at `http://127.0.0.1:8787`.

### Command Executed:
```bash
pytest -v
```

### Results Summary:
- **Total Tests Collected:** 19
- **Passed:** 19 (100%)
- **Failed:** 0
- **Duration:** 0.92 seconds

### Test Breakdown by Category:
| Test Name | File | Result | Verified Capability |
|---|---|:---:|---|
| `test_city_query_generation_international` | `test_full_suite.py` | PASS | Dynamic multi-lingual query generation (German, French, English, Custom) |
| `test_domain_deduplication_and_root_domain` | `test_full_suite.py` | PASS | Normalized root-domain deduplication and multi-suffix handling |
| `test_ssrf_and_url_safety` | `test_full_suite.py` | PASS | SSRF protection: loopback, private ranges, metadata IPs, non-HTTP blocked |
| `test_no_linkedin_scraping_and_directories_filtered` | `test_full_suite.py` | PASS | Complete exclusion of LinkedIn, social networks, and public web directories |
| `test_no_guessed_email_patterns_and_exact_evidence_validation` | `test_full_suite.py` | PASS | Hallucinated emails, numbers, and quotes are discarded unless in source text |
| `test_scoring_boundaries_and_rationales` | `test_full_suite.py` | PASS | Complete boundary tests for 100-point rubric, Tier 1/2/3, and dimension weights |
| `test_city_isolation_and_seed_preservation` | `test_full_suite.py` | PASS | All 142 Berlin seed records preserved; no cross-contamination to other cities |
| `test_excel_export_all_five_tabs` | `test_full_suite.py` | PASS | Generates valid 5-tab workbook (`Leads`, `Evidence`, `Scoring`, `Runs`, `Read Me`) |
| `test_csv_and_json_exports` | `test_full_suite.py` | PASS | Clean UTF-8 CSV and JSON exports matching all records |
| `test_ollama_status_and_repair_retry` | `test_full_suite.py` | PASS | Model list discovery, tags check, and automatic repair retry on malformed JSON |
| `test_background_job_cancellation` | `test_full_suite.py` | PASS | Safe background cancellation preserving validated records |
| `test_import_preview_and_commit` | `test_full_suite.py` | PASS | CSV/JSON preview with duplicate detection and atomic commitment |
| `test_lead_patch_persistence` | `test_full_suite.py` | PASS | CRM notes, status, contact details, and unit edits persist in SQLite |
| `test_city_changes_search_queries` | `test_research.py` | PASS | Query generation alters terms per target city |
| `test_non_german_city_uses_general_terms` | `test_research.py` | PASS | International markets default to global property management vocabulary |
| `test_score_is_bounded_and_explainable` | `test_research.py` | PASS | Dimensional breakdown matches total score |
| `test_validation_removes_unsupported_email_and_units` | `test_research.py` | PASS | Ground-truth verification resets unsupported facts to Unknown |
| `test_berlin_seed_is_loaded_with_current_conservative_score` | `test_research.py` | PASS | 142 records loaded exactly once, labeled Seeded, conservative baseline |
| `test_pipeline_saves_a_city_specific_lead_when_local_model_falls_back` | `test_research.py` | PASS | Offline fallback continues pipeline via rules-based extraction with clear labeling |

---

## 2. Live Application End-to-End Checks

1. **Launcher & Startup**:
   - `start_mac.sh` checks Python >= 3.10, prepares `.venv`, installs requirements, checks Ollama connectivity, and launches Uvicorn on `127.0.0.1:8787`.
2. **Database & Seed Loading**:
   - Fresh database created at `data/heidi_leads.db` in WAL mode.
   - Seed importer loaded all 142 Berlin prospects from `data/berlin_seed.json` on initial boot.
   - Seeded records preserved original source links, notes, and conservative scores without rewriting.
3. **API Contract Verification**:
   - `GET /api/health` -> 200 OK (returns database connection, Ollama status, search provider).
   - `GET /api/settings` -> 200 OK.
   - `PUT /api/settings` and `PATCH /api/settings` -> 200 OK (persists model and loopback base URL).
   - `POST /api/ollama/test` -> 200 OK (tests local model with lightweight structured prompt).
   - `GET /api/leads` -> 200 OK (supports filtering by city, country, search text, tier, status).
   - `PATCH /api/leads/{id}` -> 200 OK (persists contact name, role, email, phone, units, status, notes).
   - `POST /api/research` -> 200 OK (initiates asynchronous background research job).
   - `GET /api/jobs/{job_id}` -> 200 OK (returns live step progress, found count, and recent logs).
   - `POST /api/jobs/{job_id}/cancel` -> 200 OK (safely signals cancellation and marks job cancelled).
   - `GET /api/export.csv` -> 200 OK (UTF-8 CSV attachment).
   - `GET /api/export.json` -> 200 OK (Structured JSON array).
   - `GET /api/export.xlsx` -> 200 OK (5-sheet formatted Excel workbook).
   - `POST /api/import/preview` -> 200 OK (parses uploaded CSV/JSON and flags duplicate entries).
   - `POST /api/import/commit` -> 200 OK (saves new records, skips/overwrites dupes safely).

---

## 3. Security & Compliance Verification

- **Loopback Enforcement**: Default bind is `127.0.0.1`. Settings reject non-loopback Ollama URLs.
- **SSRF Defense**: `_is_public_http_url` resolves DNS hostnames and rejects private/loopback/link-local/multicast IP destinations before making requests.
- **Privacy & GDPR Compliance**: Contact details are collected only from official public company websites. LinkedIn profiles and social networks are not crawled. Guessed personal email patterns are strictly forbidden.
- **Provider Routing**: In `auto` mode, AI extraction uses the configured GroqCloud endpoint first and falls back to local Ollama. Set `AI_PROVIDER=ollama` for local-only inference. No OpenAI or Anthropic endpoint is configured by this project.

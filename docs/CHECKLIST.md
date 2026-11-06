# Heidi Lead Intelligence Agent — Implementation Checklist & Gap Audit

## 1. Baseline Audit Findings
- **Strengths Present in Initial Codebase**:
  - Clear separation of concerns (`app/db.py`, `app/research.py`, `app/ollama.py`, `app/main.py`).
  - 142 Berlin seed leads in `data/berlin_seed.json` loaded conservatively.
  - Safe localhost checking and SSRF checking in `_is_public_http_url`.
  - Basic Ollama chat prompt with structured format and validation against fetched page text.
  - 6 initial pytest tests passing.

- **Identified Gaps & Missing Requirements (Master Prompt)**:
  1. **Endpoints Missing**:
     - `GET /api/export.xlsx` (Master Prompt §7 & §10: 5 tabs: Leads, Evidence, Scoring, Research Runs, Read Me).
     - `POST /api/jobs/{job_id}/cancel` (Master Prompt §2.B, §10: Safe background job cancellation preserving validated records).
     - `POST /api/import/preview` & `POST /api/import/commit` (Master Prompt §7 & §10: Safe CSV/JSON user dataset import with preview, duplicate detection, and confirmation).
     - `POST /api/ollama/test` (Master Prompt §2.E, §10: Connection test prompt button).
     - `PATCH /api/settings` (Master Prompt §10: standard PATCH endpoint alongside PUT).
  2. **Job Cancellation & Management**:
     - Need a global/thread-safe cancellation registry/event for background jobs so when `POST /api/jobs/{job_id}/cancel` is called, `run_research` gracefully halts after the current step and marks job as `cancelled`, preserving all saved leads.
  3. **Local Ollama Model Selection & Testing**:
     - Prompt repair retry if initial JSON response is malformed.
     - `POST /api/ollama/test` with lightweight prompt test.
     - Fallback status clearly labelled as `Rules-based extraction`.
  4. **Excel Export (`.xlsx`)**:
     - Implement using `openpyxl` with tabs: `Leads`, `Evidence`, `Scoring`, `Research Runs`, `Read Me`.
     - Styling: frozen headers, column formatting, filters, clear column widths.
  5. **Import Mechanism**:
     - `POST /api/import/preview`: upload CSV or JSON, parse columns, detect duplicates against existing database (domain/city/name), return preview count and sample rows.
     - `POST /api/import/commit`: save new records with city/country scoping and transaction protection.
  6. **UI Enhancements**:
     - Add XLSX Export button in Lead Explorer and Overview.
     - Add CSV/JSON Import UI with preview modal / panel.
     - Add Cancel Job button in the active research progress card.
     - Add Test Prompt button in Settings with response display.
     - Add filters for service types, contact availability, data completeness, evidence status, and sales status in Lead Explorer.
     - Show detailed evidence drawer with tabbed or structured views (services, portfolio, contacts, metering, gaps, full sources, raw evidence).
  7. **Comprehensive Automated Test Suite**:
     - Unit tests for German vs Non-German query generation.
     - Domain deduplication, robots handling, crawl limits, timeouts, and SSRF rejection.
     - Tests proving no LinkedIn scraping and no email pattern guessing.
     - Evidence validation tests (unsupported model outputs removed or marked unknown).
     - Deterministic scoring boundary tests.
     - City isolation, seed import idempotency, lead update persistence.
     - Export tests for CSV, JSON, and XLSX (checking all 5 tabs and content).
     - Ollama mocks: model discovery, valid extraction, repair retry on malformed JSON, timeout, and offline fallback.
     - Background job progress, cancellation, and partial failure tests.
     - Import preview and commit tests.

## 2. Implementation Execution Plan
- [x] Step 1: Create Implementation Checklist artifact.
- [ ] Step 2: Implement Backend Core (`app/db.py`, `app/research.py`, `app/ollama.py`, `app/export_xlsx.py`, `app/importer.py`).
- [ ] Step 3: Implement Missing API Endpoints in `app/main.py`.
- [ ] Step 4: Upgrade Frontend UI (`static/index.html`, `static/styles.css`, `static/app.js`).
- [ ] Step 5: Write Exhaustive Pytest Test Suite covering all criteria.
- [ ] Step 6: Run Tests and Fix Any Failures.
- [ ] Step 7: Perform Live Server Execution & End-to-End Verification.
- [ ] Step 8: Update Documentation (`README.md`, `.env.example`, `docs/PRODUCT_PLAN.md`, `docs/RESEARCH_RULES.md`, `docs/ARCHITECTURE.md`, `docs/TEST_REPORT.md`, `CHANGELOG.md`).
- [ ] Step 9: Create Final Clean Distribution ZIP and Deliver Report.

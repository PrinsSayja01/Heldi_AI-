# Changelog: Heidi Lead Intelligence Agent

## [1.0.1] - 2026-11-06

- Fixed explicit Ollama model routing and selected the reliable `qwen2.5:0.5b` fallback for the current 8 GB machine.
- Added persisted research-run history to the API and dashboard.
- Expanded search-directory filtering after live runs exposed unrelated domains in DDGS results.
- Verified GroqCloud HTTP 429 fallback to Ollama without exposing credentials.
- Final suite: 30 passed.

## [1.0.0] - 2026-11-06

### Core Implementations & Functional Additions
- **5-Tab Professional Excel Export (`app/export_xlsx.py`)**:
  - Implemented `GET /api/export.xlsx` creating styled, auto-filtered openpyxl workbooks with tabs: `Leads`, `Evidence`, `Scoring`, `Research Runs`, and `Read Me`.
- **Safe Job Cancellation (`app/research.py`, `app/main.py`)**:
  - Added cancellation registry and `POST /api/jobs/{job_id}/cancel` endpoint.
  - Enabled one-click "Cancel run" button in the active research progress card that gracefully preserves already saved and validated prospects.
- **CSV & JSON Import Engine (`app/importer.py`, `app/main.py`)**:
  - Implemented `POST /api/import/preview` and `POST /api/import/commit`.
  - Built frontend Import Modal supporting drag-and-drop file upload, column normalization, duplicate detection against existing market leads, and selective overwriting.
- **Local Ollama Inference Test (`app/ollama.py`, `app/main.py`)**:
  - Added `POST /api/ollama/test` endpoint and "Test inference prompt" UI button to verify local model responsiveness without starting a crawl.
  - Implemented prompt repair retry mechanism in `analyze_company`: automatically prompts Ollama to repair malformed JSON on syntax failure.
- **Lead Explorer Filter & Export Enhancements (`static/index.html`, `static/app.js`, `static/styles.css`)**:
  - Added multi-criteria filters for Service Types (WEG, Rental, Special), Contact Availability (Named person, direct email, phone), Tier, and Sales Status.
  - Added quick-export buttons for Excel (.xlsx), CSV, and JSON directly in the Lead Explorer header.
- **API Spec & Settings Standardization**:
  - Added `PATCH /api/settings` alongside existing `PUT`.
  - Added `openpyxl` to `requirements.txt`.
- **Comprehensive Automated Test Suite (`tests/test_full_suite.py`)**:
  - Expanded test coverage from 6 to 19 tests, including SSRF verification, no-LinkedIn verification, repair retry, Excel 5-tab verification, job cancellation, and user dataset import.

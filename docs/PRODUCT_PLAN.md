# Product plan: Heidi Lead Intelligence Agent

## Product goal

Turn the Berlin Hausverwaltung case study into a repeatable, city-configurable prospecting workflow. The output is a source-backed local lead database, not a list of names without evidence.

## Target user

A small B2B sales / business-development team at a metering and heating-cost billing provider. Initial use case: find property management companies, qualify their public service fit, identify relevant public business contacts and plan follow-up research.

## User problem

Manual prospect research is slow and inconsistent. Company lists often lack verified services, disclosed portfolio size, named contacts, source citations and a repeatable qualification method. The user also needs the same workflow to work for cities other than Berlin.

## Core user journey

1. Select target city and country.
2. Choose the property-management vertical and local search vocabulary.
3. Discover company domains from public search results.
4. Retrieve a small number of relevant pages from each official site.
5. Use a local model to extract only source-supported facts.
6. Validate contact and numeric claims against retrieved content.
7. Calculate a deterministic fit score and display missing evidence.
8. Save to the city-scoped SQLite database.
9. Review / edit status and notes, then export the city list.

## Functional scope in v1

- Berlin seed import (142 leads from the existing case-study workbook).
- Configurable city, country, search terms, run size and local model.
- DDGS search adapter plus optional Serper adapter.
- Company domain de-duplication.
- Robots-aware, same-host, bounded website crawling.
- Contact extraction from public business pages only.
- Ollama local model enrichment and deterministic fallback.
- Source excerpt, URL and qualification-gap capture.
- Deterministic lead score and confidence / completeness labels.
- Dashboard, lead explorer, lead detail drawer, editable sales status and notes.
- CSV and JSON export.

## Qualification model

| Dimension | Weight | Evidence rule |
|---|---:|---|
| Service fit | 35 | WEG (15), rental (15), special-property management (5); only positive public evidence is scored |
| Portfolio scale | 25 | Disclosed managed units: <100 (5), 100-499 (10), 500-1,499 (15), 1,500-4,999 (20), 5,000+ (25) |
| Contact quality | 20 | Named person plus public professional email (20), named person (13), generic inbox (8), website contact route only (4) |
| Metering signal | 10 | Explicit remote-reading / meters / heating-cost / metering service signals |
| Evidence quality | 10 | Official company pages retrieved, multiple pages and source-matched excerpts |

The score ranks publicly visible lead evidence, not buying intent. Missing data remains visible as a gap. The app avoids assigning negative service evidence just because a page is silent.

## Local AI design

- Runtime: GroqCloud primary with Ollama API on localhost as automatic fallback.
- Default fallback model: `qwen2.5:0.5b`; an installed local model can be selected without code changes.
- Inference: one structured JSON extraction per discovered company with low temperature.
- Trust boundary: page content is untrusted. It is never allowed to alter agent instructions.
- Validation: emails must match fetched-page email strings; source URLs must be in the retrieved set; service flags and numeric portfolio claims must match page terms / values; uncertain values are cleared.
- Fallback: simple rules-based extraction keeps discovery and persistence working if Ollama is offline. The UI clearly identifies model readiness and fallback logs.

## City configuration

City and country are job-level inputs, not global constants. Search queries are rebuilt for each run. Germany uses German property-management terms by default; other countries use English terms unless the user enters local keywords. City/country is part of the database identity, so Frankfurt and Berlin records remain separate.

## Non-functional requirements

- Local-only browser bind by default.
- SQLite persistence and WAL mode.
- Bounded pages per company, request timeouts, crawl delay and robots.txt checks.
- No LinkedIn scraping or guessed contact emails.
- Evidence URLs saved with each prospect.
- Clear error and job logs.
- Human review before outbound contact.

## Deferred v2 items

- Licensed provider integrations beyond Serper (e.g. country-specific business registries).
- Entity resolution across subsidiaries, branches and multiple brands.
- Multi-user authentication, shared cloud deployment and role-based access.
- CRM sync (HubSpot / Pipedrive / Salesforce) and approval workflow.
- Email verification via a compliant verification provider.
- Scheduled refresh and stale-data alerts.
- Map radius / postcode targeting and polygon-based city boundaries.
- More precise German market filters (property type, residential units, WEG size, municipal / non-profit operators).

## Acceptance criteria

- App starts locally and loads the 142 Berlin seed leads.
- User can start a fresh research run for an arbitrary city and country.
- Search candidates are deduplicated by domain.
- Retrieved sources and evidence are visible in the lead profile.
- Local Ollama is used when available and selected.
- When Ollama is offline, app remains usable and labels the fallback.
- Lead status and notes persist after restart.
- CSV export opens in Excel / Google Sheets.
- Unit tests cover city query generation, score boundaries, and no-fabrication validation.

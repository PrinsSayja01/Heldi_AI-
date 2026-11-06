from __future__ import annotations
import io
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import config, db, research, ollama
from app.export_xlsx import generate_leads_workbook
from app.importer import preview_import, commit_import


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_heidi.db")
    monkeypatch.setattr(config, "DB_PATH", test_db)
    db.init_db()
    with TestClient(app) as c:
        yield c


def test_city_query_generation_international():
    # German query generation
    de_queries = research.build_queries("München", "Germany")
    assert any("München" in q for q in de_queries)
    assert any("Hausverwaltung" in q for q in de_queries)
    assert all("Berlin" not in q for q in de_queries)

    # French query generation
    fr_queries = research.build_queries("Paris", "France")
    assert any("Paris" in q for q in fr_queries)
    assert any("property management company" in q for q in fr_queries)

    # Custom keywords
    custom_queries = research.build_queries("Zürich", "Switzerland", ["Immobilien-Treuhand", "Liegenschaftsverwaltung"])
    assert any("Immobilien-Treuhand" in q for q in custom_queries)
    assert any("Liegenschaftsverwaltung" in q for q in custom_queries)


def test_domain_deduplication_and_root_domain():
    assert research._root_domain("www.sub.example.com") == "example.com"
    assert research._root_domain("example.co.uk") == "example.co.uk"
    assert research._root_domain("www.hausverwaltung-berlin.de") == "hausverwaltung-berlin.de"


def test_ssrf_and_url_safety():
    # Localhost, private IPs, non-HTTP should be blocked
    assert not research._is_public_http_url("http://localhost:8080/secret")
    assert not research._is_public_http_url("http://127.0.0.1:11434/api/tags")
    assert not research._is_public_http_url("http://169.254.169.254/latest/meta-data/")
    assert not research._is_public_http_url("file:///etc/passwd")
    assert not research._is_public_http_url("javascript:alert(1)")
    assert not research._is_public_http_url("http://user:pass@example.com")


def test_no_linkedin_scraping_and_directories_filtered():
    # Directory domains should be filtered from candidate exploration
    for host in ["linkedin.com", "facebook.com", "instagram.com", "yelp.com", "gelbeseiten.de"]:
        assert host in research.DIRECTORY_HOSTS
    for host in ["obsproject.com", "northdata.com", "companydata.com", "prontopro.de"]:
        assert host in research.DIRECTORY_HOSTS


def test_no_guessed_email_patterns_and_exact_evidence_validation():
    # Model returns hallucinated email and invented portfolio count
    pages = [{
        "url": "https://hv-test.de",
        "text": "Wir verwalten Liegenschaften in Berlin. Kontaktieren Sie unsere Zentrale unter zentrale@hv-test.de",
        "jsonld": "",
        "emails": ["zentrale@hv-test.de"]
    }]
    raw_model_data = {
        "company_name": "HV Test GmbH",
        "weg_management": "Yes",
        "rental_management": "Yes",
        "portfolio_units": 9999,  # hallucinated, not in text
        "contacts": [
            {"name": "Dr. Ghost CEO", "email": "ceo@hv-test.de", "email_type": "personal_work", "source_url": "https://hv-test.de"}
        ],
        "evidence": [
            {"field": "Units", "quote": "9999 Einheiten", "source_url": "https://hv-test.de"}
        ]
    }
    validated = ollama.validate_model_output(raw_model_data, pages)
    # Email not in fetched page must be stripped
    assert validated["portfolio_units"] is None
    assert validated["contacts"] == []
    # Quote not in full text must be stripped from evidence
    assert validated["evidence"] == []
    # WEG is Unknown because "weg" is not in page text
    assert validated["weg_management"] == "Unknown"


def test_scoring_boundaries_and_rationales():
    # Minimum / Empty
    empty_facts = {}
    score_res = research.calculate_score(empty_facts, [])
    assert score_res["score"] == 0
    assert score_res["tier"] == "Tier 3"

    # Tier 2 Boundary (e.g. 65 points)
    t2_facts = {
        "weg_management": "Yes", "rental_management": "Yes", # 30
        "portfolio_units": 800, # 15
        "contacts": [{"email": "info@company.de", "email_type": "generic"}], # 8
        "metering_signal": "Medium", # 5
        "evidence": [{"field": "Services", "quote": "WEG-Verwaltung und Mietverwaltung"}]
    }
    s2 = research.calculate_score(t2_facts, [{"url": "https://company.de"}])
    assert s2["score"] >= 60
    assert s2["tier"] == "Tier 2"

    # Tier 1 Boundary (80+)
    t1_facts = {
        "weg_management": "Yes", "rental_management": "Yes", "special_management": "Yes", # 35
        "portfolio_units": 5200, # 25
        "contacts": [{"name": "Erika Mustermann", "email": "erika@company.de", "email_type": "personal_work"}], # 20
        "metering_signal": "High", # 10
        "evidence": [{"field": "A", "quote": "1"}, {"field": "B", "quote": "2"}] # 10 (with 3 pages)
    }
    s1 = research.calculate_score(t1_facts, [{"url": "https://a"}, {"url": "https://b"}, {"url": "https://c"}])
    assert s1["score"] == 100
    assert s1["tier"] == "Tier 1"


def test_city_isolation_and_seed_preservation(client):
    # Verify Berlin seed is 142 leads and status is Seeded
    res_berlin = client.get("/api/leads?city=Berlin&country=Germany&limit=200")
    items_berlin = res_berlin.json()["items"]
    assert len(items_berlin) == 142
    assert all(x["status"] == "Seeded" for x in items_berlin)

    # Check that another city returns 0 leads and does not leak Berlin records
    res_ffm = client.get("/api/leads?city=Frankfurt&country=Germany")
    assert res_ffm.json()["count"] == 0


def test_excel_export_all_five_tabs(client):
    res = client.get("/api/export.xlsx?city=Berlin&country=Germany")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    # Read with openpyxl to verify all 5 tabs and data integrity
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(res.content))
    expected_sheets = ["Leads", "Evidence", "Scoring", "Research Runs", "Read Me"]
    assert wb.sheetnames == expected_sheets

    # Leads tab has 142 data rows + header = 143 rows
    ws_leads = wb["Leads"]
    assert ws_leads.max_row == 143
    assert ws_leads.cell(row=1, column=1).value == "Lead ID"
    assert ws_leads.cell(row=1, column=4).value == "Company Name"

    # Read Me tab contains compliance and rubric info
    ws_readme = wb["Read Me"]
    assert "Heidi Lead Intelligence Agent" in ws_readme.cell(row=1, column=1).value


def test_csv_and_json_exports(client):
    res_csv = client.get("/api/export.csv?city=Berlin&country=Germany")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "Lead ID" in res_csv.text or "id" in res_csv.text

    res_json = client.get("/api/export.json?city=Berlin&country=Germany")
    assert res_json.status_code == 200
    data = res_json.json()
    assert isinstance(data, list)
    assert len(data) == 142


def test_ollama_status_and_repair_retry(monkeypatch):
    # Mock Ollama status
    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self._json = json_data
            self.status_code = status_code
        def json(self): return self._json
        def raise_for_status(self): pass

    def mock_get(url, *args, **kwargs):
        if "/api/tags" in url:
            return MockResponse({"models": [{"name": "qwen3:8b"}, {"name": "gemma3:1b"}]})
        return MockResponse({}, 404)

    monkeypatch.setattr(config, "AI_PROVIDER", "ollama")
    monkeypatch.setattr("requests.get", mock_get)
    st = ollama.ollama_status()
    assert st["online"] is True
    assert "qwen3:8b" in st["models"]

    # Test repair retry on malformed JSON
    call_count = 0
    def mock_post(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First attempt returns invalid JSON
            return MockResponse({"message": {"content": "INVALID { JSON"}})
        else:
            # Repair attempt returns valid JSON
            return MockResponse({"message": {"content": '{"company_name": "Test Co", "weg_management": "Yes"}'}})

    monkeypatch.setattr("requests.post", mock_post)
    page = {"url": "https://test.co", "text": "Test Co bietet weg-verwaltung.", "jsonld": "", "emails": []}
    res = ollama.analyze_company("Test Co", "Berlin", "Germany", [page], [])
    assert call_count == 2
    assert res["weg_management"] == "Yes"


def test_ollama_test_prompt_uses_selected_model(monkeypatch):
    captured = {}

    def mock_call(messages, **kwargs):
        captured["model"] = kwargs.get("model")
        return {"content": '{"status":"ok"}', "model": kwargs.get("model"), "latency_ms": 1, "usage": {}}

    monkeypatch.setattr(ollama, "call_ollama_chat", mock_call)
    result = ollama.test_ollama_prompt("gemma3:1b")

    assert result["success"] is True
    assert result["model"] == "gemma3:1b"
    assert captured["model"] == "gemma3:1b"


def test_background_job_cancellation(client, monkeypatch):
    # Mock discover and crawl to observe cancellation flag
    def slow_discover(*args, **kwargs):
        return [
            {"domain": f"test{i}.com", "website": f"https://test{i}.com", "candidate_url": f"https://test{i}.com", "search_title": f"Test {i}", "search_sources": []}
            for i in range(1, 10)
        ]
    monkeypatch.setattr(research, "discover", slow_discover)
    
    # Request research
    res = client.post("/api/research", json={"city": "Hamburg", "country": "Germany", "max_companies": 5})
    assert res.status_code == 200
    job_id = res.json()["job_id"]

    # Cancel research immediately
    cancel_res = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["cancelled"] is True


def test_import_preview_and_commit(client):
    csv_content = """Company Name,City,Country,Website,WEG Management,Published Business Email
Neues Test HV GmbH,Frankfurt,Germany,https://neues-hv.de,Yes,kontakt@neues-hv.de
Existierende Firma,Berlin,Germany,https://existierende.de,No,info@existierende.de
"""
    files = {"file": ("test_import.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res_preview = client.post("/api/import/preview?city=Frankfurt&country=Germany", files=files)
    assert res_preview.status_code == 200
    preview_data = res_preview.json()
    assert preview_data["total_parsed"] == 2
    assert preview_data["new_count"] >= 1

    # Commit the imported items
    res_commit = client.post("/api/import/commit", json={
        "items": preview_data["all_items"],
        "overwrite_duplicates": False
    })
    assert res_commit.status_code == 200
    commit_res = res_commit.json()
    assert commit_res["inserted"] >= 1

    # Verify the imported lead is in Frankfurt
    ffm_leads = client.get("/api/leads?city=Frankfurt&country=Germany").json()["items"]
    assert any(x["name"] == "Neues Test HV GmbH" for x in ffm_leads)


def test_lead_patch_persistence(client):
    # Fetch first lead
    leads = client.get("/api/leads?city=Berlin&country=Germany&limit=1").json()["items"]
    assert leads
    lead_id = leads[0]["id"]

    # Patch fields
    patch_res = client.patch(f"/api/leads/{lead_id}", json={
        "status": "Qualified",
        "notes": "Verified portfolio size manually.",
        "portfolio_units": 450,
        "contact_person": "Frau Schmidt",
        "contact_role": "Geschäftsführerin",
        "contact_email": "schmidt@hausverwaltung.de",
        "email_type": "personal_work"
    })
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["status"] == "Qualified"
    assert updated["notes"] == "Verified portfolio size manually."
    assert updated["portfolio_units"] == 450
    assert updated["contact_person"] == "Frau Schmidt"

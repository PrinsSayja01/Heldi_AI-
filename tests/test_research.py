from app.research import build_queries, calculate_score
from app.ollama import validate_model_output


def test_city_changes_search_queries():
    queries = build_queries("Frankfurt", "Germany")
    assert queries
    assert all("Frankfurt" in q for q in queries)
    assert all("Berlin" not in q for q in queries)


def test_non_german_city_uses_general_terms():
    queries = build_queries("Amsterdam", "Netherlands")
    assert any("property management company" in q for q in queries)
    assert all("Amsterdam" in q for q in queries)


def test_score_is_bounded_and_explainable():
    facts = {
        "weg_management": "Yes", "rental_management": "Yes", "special_management": "Yes",
        "portfolio_units": 5200, "contacts": [{"name":"Max Mustermann", "email":"max.mustermann@example.de", "email_type":"personal_work"}],
        "metering_signal":"High", "evidence":[{"field":"Service","quote":"WEG-Verwaltung"},{"field":"Portfolio","quote":"5.200 Wohneinheiten"}]
    }
    result=calculate_score(facts,[{"url":"https://example.de"},{"url":"https://example.de/kontakt"},{"url":"https://example.de/leistungen"}])
    assert result["score"] == 100
    assert result["tier"] == "Tier 1"
    assert sum(result["score_breakdown"].values()) == result["score"]


def test_validation_removes_unsupported_email_and_units():
    pages=[{"url":"https://hausverwaltung.example.de","text":"Wir bieten WEG-Verwaltung in Berlin. Kontakt: info@hausverwaltung.example.de","jsonld":"","emails":["info@hausverwaltung.example.de"]}]
    output=validate_model_output({
      "company_name":"Hausverwaltung Example", "address":"Fake Street 1", "weg_management":"Yes", "rental_management":"Yes",
      "special_management":"No", "portfolio_units":850, "portfolio_buildings":14,
      "digital_portal":"Yes", "vdiv_member":"Yes", "metering_signal":"High",
      "contacts":[{"name":"Unlisted Person","role":"CEO","email":"max.mustermann@hausverwaltung.example.de","email_type":"personal_work","source_url":"https://hausverwaltung.example.de"}],
      "evidence":[{"field":"WEG","value":"Yes","quote":"Wir bieten WEG-Verwaltung in Berlin.","source_url":"https://hausverwaltung.example.de"}],
      "gaps":[]
    },pages)
    assert output["weg_management"] == "Yes"
    assert output["rental_management"] == "Unknown"
    assert output["special_management"] == "Unknown"
    assert output["portfolio_units"] is None
    assert output["portfolio_buildings"] is None
    assert output["address"] is None
    assert output["metering_signal"] == "Unknown"
    assert output["contacts"] == []
    assert output["digital_portal"] == "Unknown"
    assert output["vdiv_member"] == "Unknown"


def test_berlin_seed_is_loaded_with_current_conservative_score(tmp_path, monkeypatch):
    from app import config, db
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "seed.db"))
    db.init_db()
    items=db.list_leads(city="Berlin",country="Germany",limit=2000)
    assert len(items)==142
    assert all(x["status"]=="Seeded" for x in items)
    # The old workbook score is retained in raw data, but the app score is conservative until re-crawled.
    assert all(x["score"] <= 55 for x in items)
    assert any(x["raw"].get("original_workbook_score") is not None for x in items)

def test_pipeline_saves_a_city_specific_lead_when_local_model_falls_back(tmp_path, monkeypatch):
    from app import config, db, research
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "pipeline.db"))
    db.init_db()
    candidate={"domain":"test-hausverwaltung.example","website":"https://test-hausverwaltung.example","candidate_url":"https://test-hausverwaltung.example","search_title":"Test Hausverwaltung GmbH","search_snippet":"Hausverwaltung in Frankfurt","search_sources":[{"url":"https://search.example/result","title":"Test result","snippet":"Hausverwaltung Frankfurt"}]}
    page={"url":"https://test-hausverwaltung.example","title":"Test Hausverwaltung GmbH","text":"Test Hausverwaltung GmbH bietet WEG-Verwaltung und Mietverwaltung. Unsere Funkablesung unterstützt die Heizkostenabrechnung für 1.500 Wohneinheiten. Kontakt: kontakt@test-hausverwaltung.example","jsonld":"","emails":["kontakt@test-hausverwaltung.example"],"phones":["+49 69 12345678"],"retrieved_at":"2026-11-06T12:00:00+00:00"}
    monkeypatch.setattr(research,"discover",lambda city,country,max_companies,keywords,log:[candidate])
    monkeypatch.setattr(research,"crawl_company",lambda candidate:[page])
    def unavailable(*args,**kwargs): raise ConnectionError("Ollama is offline")
    monkeypatch.setattr(research,"analyze_company",unavailable)
    db.create_job("job-test-1","Frankfurt","Germany",1)
    research.run_research("job-test-1","Frankfurt","Germany",1,[],True)
    job=db.get_job("job-test-1")
    leads=db.list_leads(city="Frankfurt",country="Germany",limit=20)
    assert job["status"]=="completed"
    assert len(leads)==1
    lead=leads[0]
    assert lead["name"]=="Test Hausverwaltung GmbH"
    assert lead["weg_management"]=="Yes"
    assert lead["rental_management"]=="Yes"
    assert lead["portfolio_units"]==1500
    assert lead["contact_email"]=="kontakt@test-hausverwaltung.example"
    assert lead["score"]>0
    assert lead["sources"]
    assert any("rules-based extraction" in x["message"] for x in job["logs"])

from __future__ import annotations
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app import config, ai_router, ollama


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_ai.db")
    monkeypatch.setattr(config, "DB_PATH", test_db)
    from app import db
    db.init_db()
    with TestClient(app) as c:
        yield c


def test_groq_successful_inference(monkeypatch):
    """1. Groq successful inference."""
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_mock_test_key_12345")
    monkeypatch.setattr(config, "AI_PROVIDER", "groq")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"company_name": "Test Real Estate", "weg_management": "Yes"}'}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    }
    with patch("requests.post", return_value=mock_resp):
        res = ai_router.complete_chat([{"role": "user", "content": "analyze"}])
        assert res["provider"] == "groq"
        assert "Test Real Estate" in res["content"]
        assert res["usage"]["total_tokens"] == 150


def test_ollama_successful_inference(monkeypatch):
    """2. Ollama successful inference."""
    monkeypatch.setattr(config, "AI_PROVIDER", "ollama")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": '{"company_name": "Local HV GmbH", "rental_management": "Yes"}'},
        "prompt_eval_count": 80,
        "eval_count": 40
    }
    with patch("requests.post", return_value=mock_resp):
        res = ai_router.complete_chat([{"role": "user", "content": "analyze"}])
        assert res["provider"] == "ollama"
        assert "Local HV GmbH" in res["content"]
        assert res["usage"]["total_tokens"] == 120


def test_groq_429_followed_by_ollama_fallback(monkeypatch):
    """3. Groq 429 followed by Ollama fallback."""
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_mock_test_key_12345")
    monkeypatch.setattr(config, "AI_PROVIDER", "auto")
    monkeypatch.setattr(config, "AI_FALLBACK_ENABLED", True)

    # Groq returns 429
    groq_429 = MagicMock()
    groq_429.status_code = 429
    groq_429.text = "Rate limit reached"

    # Ollama returns 200
    ollama_200 = MagicMock()
    ollama_200.status_code = 200
    ollama_200.json.return_value = {
        "message": {"content": '{"fallback": true, "provider": "ollama"}'},
        "prompt_eval_count": 50,
        "eval_count": 25
    }

    def mock_post(url, *args, **kwargs):
        if "api.groq.com" in url:
            return groq_429
        return ollama_200

    with patch("requests.post", side_effect=mock_post):
        initial_fallbacks = ai_router.TELEMETRY["total_fallbacks"]
        res = ai_router.complete_chat([{"role": "user", "content": "analyze"}])
        assert res["provider"] == "ollama"
        assert ai_router.TELEMETRY["total_fallbacks"] == initial_fallbacks + 1
        assert ai_router.TELEMETRY["groq"]["cooldown_until"] > 0


def test_groq_timeout_followed_by_ollama_fallback(monkeypatch):
    """4. Groq timeout followed by Ollama fallback."""
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_mock_test_key_12345")
    monkeypatch.setattr(config, "AI_PROVIDER", "auto")
    monkeypatch.setattr(config, "AI_FALLBACK_ENABLED", True)
    # Reset cooldown
    ai_router.TELEMETRY["groq"]["cooldown_until"] = 0.0

    ollama_200 = MagicMock()
    ollama_200.status_code = 200
    ollama_200.json.return_value = {
        "message": {"content": '{"from_ollama": true}'},
        "prompt_eval_count": 30,
        "eval_count": 10
    }

    import requests
    def mock_post(url, *args, **kwargs):
        if "api.groq.com" in url:
            raise requests.exceptions.Timeout("Connection timed out")
        return ollama_200

    with patch("requests.post", side_effect=mock_post):
        res = ai_router.complete_chat([{"role": "user", "content": "analyze"}])
        assert res["provider"] == "ollama"


def test_invalid_api_key_handling(monkeypatch):
    """5. Invalid API key handling."""
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_invalid_key")
    monkeypatch.setattr(config, "AI_PROVIDER", "groq")
    monkeypatch.setattr(config, "AI_FALLBACK_ENABLED", False)
    ai_router.TELEMETRY["groq"]["cooldown_until"] = 0.0

    groq_401 = MagicMock()
    groq_401.status_code = 401
    groq_401.text = "Invalid API Key"

    with patch("requests.post", return_value=groq_401):
        with pytest.raises(PermissionError) as exc_info:
            ai_router.complete_chat([{"role": "user", "content": "test"}])
        assert "authentication failed" in str(exc_info.value).lower()


def test_both_providers_unavailable(monkeypatch):
    """6. Both providers unavailable."""
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(config, "AI_PROVIDER", "auto")
    monkeypatch.setattr(config, "AI_FALLBACK_ENABLED", True)
    ai_router.TELEMETRY["groq"]["cooldown_until"] = 0.0

    import requests
    def mock_all_fail(url, *args, **kwargs):
        raise requests.exceptions.ConnectionError("Connection refused")

    with patch("requests.post", side_effect=mock_all_fail):
        with pytest.raises(requests.exceptions.ConnectionError):
            ai_router.complete_chat([{"role": "user", "content": "test"}])


def test_invalid_structured_json_repair(monkeypatch):
    """7. Invalid structured JSON repair."""
    monkeypatch.setattr(config, "AI_PROVIDER", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk_test")
    ai_router.TELEMETRY["groq"]["cooldown_until"] = 0.0

    call_count = 0
    def mock_groq_repair(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.status_code = 200
        if call_count == 1:
            resp.json.return_value = {"choices": [{"message": {"content": "MALFORMED { JSON"}}]}
        else:
            resp.json.return_value = {"choices": [{"message": {"content": '{"company_name": "Repaired GmbH", "weg_management": "Yes"}'}}]}
        return resp

    page = [{"url": "https://repaired.de", "text": "Repaired GmbH bietet weg-verwaltung.", "jsonld": "", "emails": []}]
    with patch("requests.post", side_effect=mock_groq_repair):
        res = ollama.analyze_company("Repaired GmbH", "Berlin", "Germany", page, [])
        assert call_count == 2
        assert res["company_name"] == "Repaired GmbH"
        assert res["weg_management"] == "Yes"


def test_provider_switching_from_dashboard(client):
    """8. Provider switching from dashboard."""
    # Switch to groq
    r = client.put("/api/settings", json={"ai_provider": "groq", "groq_model": "openai/gpt-oss-120b"})
    assert r.status_code == 200
    assert r.json()["ai_provider"] == "groq"
    assert config.AI_PROVIDER == "groq"

    # Switch to ollama
    r2 = client.patch("/api/settings", json={"ai_provider": "ollama"})
    assert r2.status_code == 200
    assert r2.json()["ai_provider"] == "ollama"
    assert config.AI_PROVIDER == "ollama"

    # Switch to auto
    r3 = client.put("/api/settings", json={"ai_provider": "auto"})
    assert r3.status_code == 200
    assert r3.json()["ai_provider"] == "auto"
    assert config.AI_PROVIDER == "auto"


def test_api_key_protection(client, monkeypatch):
    """9. API key protection: key is never returned to frontend."""
    real_key = "gsk_super_secret_production_key_abcdef123456"
    monkeypatch.setattr(config, "GROQ_API_KEY", real_key)

    # Check /api/health
    h = client.get("/api/health").json()
    assert real_key not in json.dumps(h)
    assert h["ai"]["groq"]["masked_key"] == "gsk_...3456"

    # Check /api/settings
    s = client.get("/api/settings").json()
    assert real_key not in json.dumps(s)
    assert s["ai"]["groq"]["masked_key"] == "gsk_...3456"

    # Check /api/ai/status
    st = client.get("/api/ai/status").json()
    assert real_key not in json.dumps(st)
    assert st["groq"]["masked_key"] == "gsk_...3456"


def test_research_data_preservation_during_fallback(monkeypatch, tmp_path):
    """10. Research data preservation during fallback."""
    from app import db, research
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "fallback_preserve.db"))
    db.init_db()

    candidate = {
        "domain": "preserve-test.de", "website": "https://preserve-test.de",
        "candidate_url": "https://preserve-test.de", "search_title": "Preserve Test GmbH",
        "search_snippet": "HV in Berlin", "search_sources": []
    }
    page = {
        "url": "https://preserve-test.de", "title": "Preserve Test",
        "text": "Preserve Test GmbH bietet Mietverwaltung. Kontakt: info@preserve-test.de",
        "jsonld": "", "emails": ["info@preserve-test.de"], "phones": []
    }

    monkeypatch.setattr(research, "discover", lambda city, country, max_co, kw, log: [candidate])
    monkeypatch.setattr(research, "crawl_company", lambda cand: [page])

    # Groq fails, Ollama succeeds
    def mock_analyze(company, city, country, pages, snippets):
        ai_router.record_fallback("groq", "ollama", "Mocked quota limit")
        return {
            "company_name": "Preserve Test GmbH", "rental_management": "Yes",
            "contacts": [{"name": None, "email": "info@preserve-test.de", "email_type": "generic"}],
            "evidence": [], "gaps": []
        }

    monkeypatch.setattr(research, "analyze_company", mock_analyze)

    db.create_job("job-preserve-1", "Berlin", "Germany", 1)
    research.run_research("job-preserve-1", "Berlin", "Germany", 1, [], True)

    leads = db.list_leads(city="Berlin", country="Germany", limit=200)
    assert any(x["name"] == "Preserve Test GmbH" for x in leads)
    job = db.get_job("job-preserve-1")
    assert job["status"] == "completed"
    assert job["found"] == 1

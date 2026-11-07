from __future__ import annotations
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
import requests
from . import config

LOG = logging.getLogger("heidi.ai_router")

# Global Usage & Telemetry Tracker
TELEMETRY = {
    "groq": {
        "requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "last_success_at": None,
        "last_error": None,
        "last_latency_ms": None,
        "cooldown_until": 0.0,
    },
    "ollama": {
        "requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "last_success_at": None,
        "last_error": None,
        "last_latency_ms": None,
        "cooldown_until": 0.0,
    },
    "fallback_events": [],
    "total_fallbacks": 0,
}

COOLDOWN_DURATION_SECONDS = 60.0  # Cooldown after 429/quota exhaustion


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_masked_key(key: str) -> str:
    if not key:
        return "Not configured"
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


def get_ai_status() -> dict:
    """Returns runtime AI provider configuration, health, and usage telemetry without exposing keys."""
    now = time.time()
    groq_cooldown = max(0, int(TELEMETRY["groq"]["cooldown_until"] - now))
    ollama_cooldown = max(0, int(TELEMETRY["ollama"]["cooldown_until"] - now))

    groq_configured = bool(config.GROQ_API_KEY)
    
    # Check Ollama tags for models
    ollama_online = False
    ollama_models = []
    if not config.IS_PRODUCTION and not config.IS_DEMO:
        try:
            r = requests.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=2)
            if r.status_code == 200:
                ollama_online = True
                ollama_models = [m.get("name") for m in r.json().get("models", []) if m.get("name")]
        except Exception:
            ollama_online = False

    return {
        "online": ollama_online,  # legacy compatibility
        "models": ollama_models,  # legacy compatibility
        "provider_mode": config.AI_PROVIDER,  # 'auto', 'groq', 'ollama'
        "fallback_enabled": config.AI_FALLBACK_ENABLED,
        "fallback_provider": config.AI_FALLBACK_PROVIDER,
        "groq": {
            "configured": groq_configured,
            "masked_key": get_masked_key(config.GROQ_API_KEY),
            "model": config.GROQ_MODEL,
            "base_url": config.GROQ_BASE_URL,
            "in_cooldown": groq_cooldown > 0,
            "cooldown_remaining_seconds": groq_cooldown,
            "stats": TELEMETRY["groq"],
        },
        "ollama": {
            "online": ollama_online,
            "base_url": config.OLLAMA_BASE_URL,
            "model": config.OLLAMA_MODEL,
            "models": ollama_models,
            "available_models": ollama_models,
            "in_cooldown": ollama_cooldown > 0,
            "cooldown_remaining_seconds": ollama_cooldown,
            "stats": TELEMETRY["ollama"],
        },
        "telemetry": {
            "total_fallbacks": TELEMETRY["total_fallbacks"],
            "recent_fallback_events": TELEMETRY["fallback_events"][-10:],
        }
    }


def record_fallback(from_provider: str, to_provider: str, reason: str):
    TELEMETRY["total_fallbacks"] += 1
    event = {
        "at": now_iso(),
        "from": from_provider,
        "to": to_provider,
        "reason": reason[:200]
    }
    TELEMETRY["fallback_events"].append(event)
    LOG.warning(f"AI Provider Fallback: Switched from {from_provider} to {to_provider}. Reason: {reason}")


def call_groq_chat(messages: list[dict], temperature: float = 0.1, json_format: bool = True, timeout: int | None = None) -> dict:
    """Executes a chat completion against GroqCloud."""
    if not config.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured in backend environment.")

    now = time.time()
    if TELEMETRY["groq"]["cooldown_until"] > now:
        remaining = int(TELEMETRY["groq"]["cooldown_until"] - now)
        raise RuntimeError(f"GroqCloud is in cooldown for {remaining}s due to recent rate limit or outage.")

    TELEMETRY["groq"]["requests"] += 1
    t0 = time.time()
    
    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload: dict[str, Any] = {
        "model": config.GROQ_MODEL,
        "messages": messages,
        "temperature": temperature
    }
    if json_format:
        payload["response_format"] = {"type": "json_object"}

    effective_timeout = timeout or config.GROQ_TIMEOUT_SECONDS

    try:
        r = requests.post(f"{config.GROQ_BASE_URL}/chat/completions", json=payload, headers=headers, timeout=effective_timeout)
        latency = int((time.time() - t0) * 1000)
        TELEMETRY["groq"]["last_latency_ms"] = latency

        if r.status_code == 429:
            TELEMETRY["groq"]["failed_requests"] += 1
            TELEMETRY["groq"]["cooldown_until"] = time.time() + COOLDOWN_DURATION_SECONDS
            TELEMETRY["groq"]["last_error"] = "Rate limit reached (429)"
            raise RuntimeError("GroqCloud rate limit / quota exceeded (HTTP 429). Entering cooldown.")
        
        if r.status_code >= 500:
            TELEMETRY["groq"]["failed_requests"] += 1
            TELEMETRY["groq"]["cooldown_until"] = time.time() + 30.0
            TELEMETRY["groq"]["last_error"] = f"Server error ({r.status_code})"
            raise RuntimeError(f"GroqCloud service unavailable ({r.status_code}).")

        if r.status_code in (401, 403):
            TELEMETRY["groq"]["failed_requests"] += 1
            TELEMETRY["groq"]["last_error"] = f"Authentication error ({r.status_code})"
            raise PermissionError(f"GroqCloud authentication failed (HTTP {r.status_code}): Invalid or expired API key.")

        r.raise_for_status()
        data = r.json()

        usage = data.get("usage") or {}
        p_tok = usage.get("prompt_tokens") or 0
        c_tok = usage.get("completion_tokens") or 0
        tot_tok = usage.get("total_tokens") or (p_tok + c_tok)
        
        TELEMETRY["groq"]["successful_requests"] += 1
        TELEMETRY["groq"]["prompt_tokens"] += p_tok
        TELEMETRY["groq"]["completion_tokens"] += c_tok
        TELEMETRY["groq"]["total_tokens"] += tot_tok
        TELEMETRY["groq"]["last_success_at"] = now_iso()
        TELEMETRY["groq"]["last_error"] = None

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {
            "content": content,
            "provider": "groq",
            "model": config.GROQ_MODEL,
            "latency_ms": latency,
            "usage": usage
        }

    except requests.exceptions.Timeout as exc:
        latency = int((time.time() - t0) * 1000)
        TELEMETRY["groq"]["failed_requests"] += 1
        TELEMETRY["groq"]["last_latency_ms"] = latency
        TELEMETRY["groq"]["last_error"] = "Request timeout"
        raise TimeoutError(f"GroqCloud request timed out after {effective_timeout}s.") from exc
    except (requests.exceptions.ConnectionError, requests.exceptions.RequestException) as exc:
        latency = int((time.time() - t0) * 1000)
        TELEMETRY["groq"]["failed_requests"] += 1
        TELEMETRY["groq"]["last_latency_ms"] = latency
        TELEMETRY["groq"]["last_error"] = str(exc)[:120]
        raise


def call_ollama_chat(messages: list[dict], temperature: float = 0.1, json_format: bool = True, timeout: int | None = None, model: str | None = None) -> dict:
    """Executes a chat completion against local Ollama."""
    if config.IS_PRODUCTION or config.IS_DEMO:
        raise RuntimeError("Local Ollama is disabled in production; configure GroqCloud or a cloud fallback.")
    TELEMETRY["ollama"]["requests"] += 1
    t0 = time.time()
    effective_timeout = timeout or config.OLLAMA_TIMEOUT_SECONDS

    selected_model = (model or config.OLLAMA_MODEL).strip()
    payload: dict[str, Any] = {
        "model": selected_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": 1800}
    }
    if json_format:
        payload["format"] = "json"

    try:
        r = requests.post(f"{config.OLLAMA_BASE_URL}/api/chat", json=payload, timeout=effective_timeout)
        latency = int((time.time() - t0) * 1000)
        TELEMETRY["ollama"]["last_latency_ms"] = latency

        r.raise_for_status()
        data = r.json()

        p_tok = data.get("prompt_eval_count") or 0
        c_tok = data.get("eval_count") or 0
        tot_tok = p_tok + c_tok

        TELEMETRY["ollama"]["successful_requests"] += 1
        TELEMETRY["ollama"]["prompt_tokens"] += p_tok
        TELEMETRY["ollama"]["completion_tokens"] += c_tok
        TELEMETRY["ollama"]["total_tokens"] += tot_tok
        TELEMETRY["ollama"]["last_success_at"] = now_iso()
        TELEMETRY["ollama"]["last_error"] = None

        content = data.get("message", {}).get("content", "")
        return {
            "content": content,
            "provider": "ollama",
            "model": selected_model,
            "latency_ms": latency,
            "usage": {"prompt_tokens": p_tok, "completion_tokens": c_tok, "total_tokens": tot_tok}
        }
    except Exception as exc:
        latency = int((time.time() - t0) * 1000)
        TELEMETRY["ollama"]["failed_requests"] += 1
        TELEMETRY["ollama"]["last_latency_ms"] = latency
        TELEMETRY["ollama"]["last_error"] = str(exc)[:120]
        raise


def complete_chat(messages: list[dict], temperature: float = 0.1, json_format: bool = True, timeout: int | None = None) -> dict:
    """
    Unified router with automatic fallback logic:
    1. If AI_PROVIDER == 'groq': try Groq only.
    2. If AI_PROVIDER == 'ollama': try Ollama only.
    3. If AI_PROVIDER == 'auto': try Groq first. If rate limit (429), quota exhaustion, timeout,
       or connection failure occurs, switch automatically to Ollama.
    """
    mode = config.AI_PROVIDER.lower()

    if mode == "groq":
        return call_groq_chat(messages, temperature=temperature, json_format=json_format, timeout=timeout)
    
    if mode == "ollama":
        return call_ollama_chat(messages, temperature=temperature, json_format=json_format, timeout=timeout)

    # mode == 'auto'
    if not config.GROQ_API_KEY:
        LOG.info("AI_PROVIDER is auto, but GROQ_API_KEY is not set. Routing directly to local Ollama.")
        return call_ollama_chat(messages, temperature=temperature, json_format=json_format, timeout=timeout)

    try:
        return call_groq_chat(messages, temperature=temperature, json_format=json_format, timeout=timeout)
    except PermissionError as p_err:
        # Authentication error (invalid key) -> log and fallback if enabled
        if config.AI_FALLBACK_ENABLED:
            if config.IS_PRODUCTION:
                raise RuntimeError("GroqCloud authentication failed and no cloud AI fallback is configured.") from p_err
            record_fallback("groq", "ollama", f"Auth failure: {str(p_err)}")
            return call_ollama_chat(messages, temperature=temperature, json_format=json_format, timeout=timeout)
        raise
    except Exception as exc:
        if config.AI_FALLBACK_ENABLED:
            if config.IS_PRODUCTION:
                raise RuntimeError("GroqCloud is unavailable and no cloud AI fallback is configured.") from exc
            record_fallback("groq", "ollama", str(exc))
            return call_ollama_chat(messages, temperature=temperature, json_format=json_format, timeout=timeout)
        raise

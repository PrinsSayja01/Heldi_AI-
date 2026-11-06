from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8787"))
DB_PATH = os.getenv("DATABASE_PATH", str(ROOT / "data" / "heidi_leads.db"))

# AI Provider Configuration
AI_PROVIDER = os.getenv("AI_PROVIDER", "auto").strip().lower() # 'auto', 'groq', 'ollama'
AI_FALLBACK_ENABLED = os.getenv("AI_FALLBACK_ENABLED", "true").strip().lower() in ("true", "1", "yes")
AI_FALLBACK_PROVIDER = os.getenv("AI_FALLBACK_PROVIDER", "ollama").strip().lower()

# Primary Provider: Groq Cloud
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_TIMEOUT_SECONDS = int(os.getenv("GROQ_TIMEOUT_SECONDS", "30"))

# Fallback Provider: Local Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b").strip()
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "150"))

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
MAX_PAGES_PER_COMPANY = max(1, min(int(os.getenv("MAX_PAGES_PER_COMPANY", "4")), 6))
REQUEST_TIMEOUT_SECONDS = max(5, min(int(os.getenv("REQUEST_TIMEOUT_SECONDS", "12")), 30))
CRAWL_DELAY_SECONDS = max(0.2, min(float(os.getenv("CRAWL_DELAY_SECONDS", "0.6")), 3.0))
SEED_PATH = ROOT / "data" / "berlin_seed.json"
STATIC_PATH = ROOT / "static"

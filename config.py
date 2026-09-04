import os
from dotenv import load_dotenv

load_dotenv()

def _clean_key(val: str) -> str:
    if not val:
        return ""
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1].strip()
    return val

# ── LLM Configuration ──────────────────────────────────────────────
GEMINI_API_KEY = _clean_key(os.getenv("GEMINI_API_KEY", ""))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

def get_api_key() -> str:
    return _clean_key(os.getenv("GEMINI_API_KEY", GEMINI_API_KEY))

# ── Bot Metadata ────────────────────────────────────────────────────
TEAM_NAME = "Sonal"
TEAM_MEMBERS = ["Sonal"]
MODEL_NAME = GEMINI_MODEL
APPROACH = "4-context deterministic composer with Gemini LLM: dispatch by trigger.kind, ground every output in received context, single low-friction CTA"
BOT_VERSION = "1.0.0"

# ── Server Configuration ───────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ── Timeouts & Limits ──────────────────────────────────────────────
LLM_TIMEOUT_SECONDS = 25          # leave 5s buffer under the 30s judge timeout
MAX_ACTIONS_PER_TICK = 20

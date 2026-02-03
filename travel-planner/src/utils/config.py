"""Load and validate environment variables. Uses python-dotenv.

This module is intentionally thin and side-effect free except for loading `.env`.
Callers should use the accessor functions below rather than reading `os.environ`
directly, to keep environment handling consistent.
"""

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import os


def _project_root() -> Path:
    """Resolve project root (travel-planner/)."""
    return Path(__file__).resolve().parent.parent.parent


def load_config() -> None:
    """
    Load .env from project root. Idempotent; safe to call multiple times.
    Uses override=True to ensure .env values take precedence over existing env vars.
    """
    root = _project_root()
    env_path = root / ".env"
    load_dotenv(env_path, override=True)


def get_required(key: str) -> str:
    """
    Get required env var. Raises if missing or empty.

    Raises:
        ValueError: If key is missing or empty after trimming.
    """
    load_config()
    val = os.getenv(key, "").strip()
    if not val:
        raise ValueError(
            f"Missing required environment variable: {key}. "
            "Set it in .env or export it."
        )
    return val


def get_optional(key: str, default: str = "") -> str:
    """Get optional env var; return default if missing or empty."""
    load_config()
    val = os.getenv(key, "").strip()
    return val if val else default


def get_optional_int(key: str, default: int) -> int:
    """Get optional env var as int; return default if missing or invalid."""
    load_config()
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# --- Public config accessors ---

def grok_api_key() -> str:
    """Required: Grok API key for xAI (when LLM_PROVIDER=grok)."""
    return get_required("GROK_API_KEY")


def groq_api_key() -> str:
    """Required: Groq API key (when LLM_PROVIDER=groq)."""
    return get_required("GROQ_API_KEY")


def llm_provider() -> str:
    """Optional: LLM provider. Default grok (xAI). Use groq for free tier (Llama via Groq)."""
    return get_optional("LLM_PROVIDER", "grok").lower().strip()


def llm_base_url() -> str:
    """Chat completions URL for the active LLM provider."""
    if llm_provider() == "groq":
        return "https://api.groq.com/openai/v1/chat/completions"
    return "https://api.x.ai/v1/chat/completions"


def llm_api_key() -> str:
    """API key for the active LLM provider."""
    if llm_provider() == "groq":
        return groq_api_key()
    return grok_api_key()


def llm_model() -> str:
    """Model name for the active LLM provider."""
    if llm_provider() == "groq":
        return get_optional("GROQ_MODEL", "llama-3.3-70b-versatile")
    return get_optional("GROK_MODEL", "grok-4-1-fast")


def n8n_webhook_url() -> str | None:
    """Optional: n8n webhook URL for PDF/email automation."""
    val = get_optional("N8N_WEBHOOK_URL", "")
    return val or None


def n8n_api_url() -> str | None:
    """Optional: n8n API URL for MCP server integration."""
    val = get_optional("N8N_API_URL", "")
    return val or None


def n8n_api_key() -> str | None:
    """Optional: n8n API key for MCP server integration."""
    val = get_optional("N8N_API_KEY", "")
    return val or None


def overpass_max_requests() -> int:
    """
    Optional: max Overpass API requests per session. Default 2.
    Checks OVERPASS_MAX_REQUESTS first, then OVERPASS_MAX_REQUESTS_PER_SESSION.
    """
    load_config()
    v = os.getenv("OVERPASS_MAX_REQUESTS", "").strip()
    if v:
        try:
            return int(v)
        except ValueError:
            pass
    v = os.getenv("OVERPASS_MAX_REQUESTS_PER_SESSION", "").strip()
    if v:
        try:
            return int(v)
        except ValueError:
            pass
    return 2


def target_city() -> str:
    """Optional: target city. Default Udaipur."""
    return get_optional("TARGET_CITY", "Udaipur")


def max_itinerary_days() -> int:
    """Optional: max itinerary days. Default 4."""
    return get_optional_int("MAX_ITINERARY_DAYS", 4)


def grok_model() -> str:
    """Optional: Grok model name. Default grok-4-1-fast (xAI Grok 4.1)."""
    return get_optional("GROK_MODEL", "grok-4-1-fast")


def llm_max_tokens() -> int:
    """Optional: max tokens for LLM responses. Default 4000."""
    return get_optional_int("GROK_MAX_TOKENS", 4000)


def grok_max_tokens() -> int:
    """Optional: max tokens for LLM responses. Default 4000. Alias for llm_max_tokens."""
    return llm_max_tokens()


def project_root() -> Path:
    """Project root directory (travel-planner/)."""
    return _project_root()

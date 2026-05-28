"""
Bot configuration loaded from environment variables.
Mirrors the logic in the original config/index.js.
"""

import json
import os
import re


def _parse_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _parse_role_map(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _to_positive_int(value: str | None, fallback: int) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
        return n if n > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _normalize_api_url(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().rstrip("/")
    # Strip trailing /api suffix — endpoint paths add /api themselves.
    normalized = re.sub(r"/api$", "", normalized, flags=re.IGNORECASE)
    return normalized or None


class Config:
    def __init__(self) -> None:
        self.discord_token: str | None = os.getenv("DISCORD_TOKEN")
        self.discord_client_id: str | None = os.getenv("DISCORD_CLIENT_ID")
        self.discord_guild_id: str | None = os.getenv("DISCORD_GUILD_ID")
        self.command_prefix: str = os.getenv("COMMAND_PREFIX") or "!"
        self.admin_role_name: str = os.getenv("ADMIN_ROLE_NAME") or "Admin"
        self.log_channel_ids: list[str] = _parse_list(os.getenv("LOG_CHANNEL_IDS"))
        self.api_base_url: str | None = _normalize_api_url(
            os.getenv("SILVERSHADE_API") or os.getenv("API_BASE_URL")
        )
        self.api_key: str | None = os.getenv("SILVERSHADE_API_KEY") or os.getenv("API_KEY")
        self.admin_token: str | None = os.getenv("SILVERSHADE_ADMIN_TOKEN")
        # JS uses POLL_INTERVAL_MS; convert to seconds with a 5 000 ms default.
        self.poll_interval_seconds: float = (
            _to_positive_int(os.getenv("POLL_INTERVAL_MS"), 5000) / 1000
        )
        self.backend_role_map: dict[str, str] = _parse_role_map(os.getenv("BACKEND_ROLE_MAP"))


def validate_config(cfg: Config) -> None:
    required = [
        ("DISCORD_TOKEN", cfg.discord_token),
        ("DISCORD_GUILD_ID", cfg.discord_guild_id),
        ("SILVERSHADE_API", cfg.api_base_url),
        ("SILVERSHADE_API_KEY", cfg.api_key),
    ]
    missing = [key for key, val in required if not val]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

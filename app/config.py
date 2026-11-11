"""
Configuration for the Cerebro MCP client.

Loads settings from:
  1. .cerebro/config.json in the vault (highest priority)
  2. Environment variables
  3. Defaults
"""

from enum import Enum
from pydantic import Field, AliasChoices, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.logging_config import setup_logging

logger = setup_logging()


DEFAULT_REVIEW_INTERVALS = [1, 3, 7, 14, 30, 60, 120]

class AppBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        enable_decoding=False,
    )

class watchdog_config(AppBaseSettings):
    """Configuration for the watchdog file watcher."""

    # Path to the Obsidian vault folder to watch for changes
    vault_path: str = Field(default="", validation_alias=AliasChoices("vault_path", "obsidian_vault_path"))

    # Patterns to watch for changes (glob patterns)
    watch_patterns: str = "*.md"

    # Debounce time in seconds to avoid rapid successive events
    debounce_seconds: float = Field(default=1.0, validation_alias=AliasChoices("debounce_seconds", "watch_debounce_seconds"))
    poll_interval_seconds: float = Field(default=2.0, validation_alias=AliasChoices("poll_interval_seconds", "watch_poll_interval_seconds"))

    @property
    def vault_folder_path(self) -> str:
        return self.vault_path

class telegram_config(AppBaseSettings):
    """Configuration for the Telegram bot."""

    # Telegram bot token
    telegram_bot_token: str = ""


    # Time of day to send reminders (HH:MM format)
    reminder_time: str = Field(default="09:00", validation_alias=AliasChoices("reminder_time", "telegram_reminder_time"))

    allowed_user_ids: str = Field(default="", validation_alias=AliasChoices("allowed_user_ids", "telegram_allowed_users"))

    @property
    def allowed_user_id_list(self) -> list[int]:
        return [int(item.strip()) for item in self.allowed_user_ids.split(",") if item.strip()]

class llm_config(AppBaseSettings):
    """Configuration for the local LLM (Ollama) used for question/feedback generation."""

    # Local Ollama chat model used for question/feedback generation
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "gemma4"
    embedding_model: str = "nomic-embed-text"
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-2.5-flash"
    llm_provider: str = "ollama"

class Obsidian_http_config(AppBaseSettings):
    """Configuration for the Obsidian HTTP/MCP-compatible server."""

    # Already-running Obsidian HTTP/MCP-compatible server
    obsidian_http_url: str = "https://localhost:27124"
    obsidian_http_token: str = ""
    obsidian_http_verify_tls: bool = False

class postgres_config(AppBaseSettings):
    """Configuration for the PostgreSQL database."""

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "cerebro"
    postgres_password: str = ""
    postgres_database: str = Field(
        default="cerebro",
        validation_alias=AliasChoices("postgres_database", "postgres_db")
    )
    postgres_min_pool_size: int = 1
    postgres_max_pool_size: int = 10

    @property
    def postgres_db(self) -> str:
        return self.postgres_database

class CerebroConfig(AppBaseSettings):
    """Configuration for the Cerebro MCP client and vault settings."""
    vault_path: str = ""
    notes_dir: str = ""
    mcp_command: str = "npx"
    mcp_args: str | list[str] = Field(default_factory=lambda: ["-y", "obsidian-mcp-server"])
    schedule_file: str = "cerebro_schedule.json"
    review_log_dir: str = "cerebro_reviews"
    review_intervals: list[int] = Field(default_factory=lambda: [1, 3, 7, 14, 30, 60, 120])

    @field_validator("mcp_args", mode="after")
    @classmethod
    def parse_mcp_args(cls, v: object) -> list[str]:
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                import json
                try:
                    return json.loads(v_str)
                except Exception:
                    pass
            return [arg.strip() for arg in v_str.split(",") if arg.strip()]
        return v  # type: ignore[return-value]

    @field_validator("review_intervals", mode="before")
    @classmethod
    def parse_review_intervals(cls, value: object) -> list[int]:
        if isinstance(value, str):
            import json
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [int(item) for item in parsed]
            except Exception:
                pass
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        return value  # type: ignore[return-value]


class AppSettings:
    def __init__(self):
        self.watchdog = watchdog_config()
        self.telegram = telegram_config()
        self.llm = llm_config()
        self.obsidian_http = Obsidian_http_config()
        self.postgres = postgres_config()
        self.cerebro = CerebroConfig()

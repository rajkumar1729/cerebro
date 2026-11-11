"""Cerebro Client — re-exports from all subpackages."""

from .db import PostgreSQLClient, initialize_postgres_schema
from .embedding import OllamaEmbeddingClient

try:
    from .mcp import ObsidianMCPClient
except ModuleNotFoundError:
    ObsidianMCPClient = None

try:
    from .telegram import TelegramBotClient
except (ModuleNotFoundError, ImportError):
    TelegramBotClient = None

__all__ = [
    # db
    "PostgreSQLClient",
    "initialize_postgres_schema",
    # embedding
    "OllamaEmbeddingClient",
    "ObsidianMCPClient",
    # telegram
    "TelegramBotClient",
]

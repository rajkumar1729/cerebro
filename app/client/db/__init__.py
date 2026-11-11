"""Database client package for Cerebro (PostgreSQL)."""
from .pg_client import PostgreSQLClient


def initialize_postgres_schema(client: PostgreSQLClient | None = None) -> PostgreSQLClient:
    """Convenience helper to initialize PostgreSQL schema tables."""
    db = client or PostgreSQLClient()
    return db.initialize_postgres_schema()


__all__ = [
    "PostgreSQLClient",
    "initialize_postgres_schema",
]

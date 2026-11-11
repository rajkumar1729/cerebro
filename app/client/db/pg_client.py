"""
PostgreSQLClient — Generic, reusable PostgreSQL client.

Provides a clean abstraction over psycopg with:
  • Connection pooling and management
  • Dict-based row access (dict_row)
  • Convenience methods: insert, upsert, update, fetch_one, fetch_all
  • Explicit transaction context manager
  • Version-tracked schema migrations

Configuration is loaded from .env file via app.config.postgres_config:
  POSTGRES_HOST (default: localhost)
  POSTGRES_PORT (default: 5432)
  POSTGRES_DATABASE (default: cerebro)
  POSTGRES_USER (default: cerebro)
  POSTGRES_PASSWORD (default: "")
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator, Sequence

import psycopg
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from ...config import postgres_config

logger = logging.getLogger(__name__)


class _PooledCursor:
    """Cursor proxy that returns its checked-out connection when closed."""
    def __init__(self, cursor: Any, pool: ConnectionPool, connection: Any):
        self._cursor, self._pool, self._connection = cursor, pool, connection

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    def close(self) -> None:
        if self._connection is not None:
            self._cursor.close()
            self._pool.putconn(self._connection)
            self._connection = None

DEFAULT_SCHEMA_MIGRATIONS: list[str] = []

class PostgreSQLClient:
    """
    Generic PostgreSQL client with connection management, convenience
    query methods, and schema migration support.

    Connection settings are loaded from .env file via app.config.postgres_config.
    Optional parameters can override .env values.

    .env file should contain::

        POSTGRES_HOST=localhost
        POSTGRES_PORT=5432
        POSTGRES_DATABASE=cerebro
        POSTGRES_USER=cerebro
        POSTGRES_PASSWORD=password

    Usage::

        from app.client.db import PostgreSQLClient

        db = PostgreSQLClient()  # Loads from app config
        db.migrate([
            "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, name TEXT)",
        ])

        db.insert("users", {"name": "Alice"})
        row = db.fetch_one("SELECT * FROM users WHERE name = %s", ("Alice",))
        print(row["name"])  # "Alice"

        db.close()
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        # Load from app config (.env file)
        config = postgres_config()

        # Use provided parameters or fall back to config
        self.host = host or config.postgres_host
        self.port = port or config.postgres_port
        self.database = database or config.postgres_database
        self.user = user or config.postgres_user
        self.password = password or config.postgres_password
        self.pool = ConnectionPool(
            min_size=config.postgres_min_pool_size,
            max_size=config.postgres_max_pool_size,
            kwargs={"host": self.host, "port": self.port, "dbname": self.database,
                    "user": self.user, "password": self.password, "row_factory": dict_row},
            open=True,
        )
        self.pool.wait(timeout=30)
        logger.info(
            "PostgreSQLClient ready at %s:%d/%s",
            self.host,
            self.port,
            self.database,
        )

    # ── Connection lifecycle ──────────────────────────────────

    def _connect(self) -> None:
        """Compatibility hook; connections are opened and recycled by the pool."""
        self.pool.wait(timeout=30)

    @property
    def connection(self) -> psycopg.Connection[Any]:
        """Return a pooled connection. Prefer transaction() for scoped access."""
        return self.pool.getconn()

    def close(self) -> None:
        """Close the database connection."""
        self.pool.close()
        logger.info("PostgreSQL pool closed (%s:%d/%s)", self.host, self.port, self.database)

    # ── Transaction support ───────────────────────────────────

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """
        Context manager for an explicit transaction.

        Commits on clean exit, rolls back on exception.

        Usage::

            with db.transaction() as cursor:
                cursor.execute("INSERT INTO t VALUES (%s)", (1,))
                cursor.execute("INSERT INTO t VALUES (%s)", (2,))
        """
        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cursor:
                    yield cursor
        except Exception as e:
            logger.error("Transaction failed, rolled back: %s", e)
            raise

    # ── Raw execute ───────────────────────────────────────────

    def execute(
        self,
        sql: str,
        params: Sequence[Any] = (),
    ) -> Any:
        """
        Execute SQL and return the cursor. Caller is responsible
        for closing the cursor.

        Args:
            sql: SQL query (use %s for parameterized values)
            params: Query parameters

        Returns:
            psycopg cursor (dict_row for dict-based access)
        """
        # Retained for compatibility; callers must close the cursor and return
        # its connection with close_cursor(). Internal reads use pooled scopes.
        conn = self.pool.getconn()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return _PooledCursor(cursor, self.pool, conn)
        except psycopg.Error as e:
            self.pool.putconn(conn)
            logger.error("Query failed: %s | SQL: %s", e, sql)
            raise

    def close_cursor(self, cursor: Any) -> None:
        cursor.close()

    # ── Fetch methods ─────────────────────────────────────────

    def fetch_one(
        self,
        sql: str,
        params: Sequence[Any] = (),
    ) -> dict[str, Any] | None:
        """
        Execute SQL and return the first row as a dict, or None.

        Args:
            sql: SQL query
            params: Query parameters

        Returns:
            First row as dict, or None if no rows
        """
        with self.pool.connection() as conn, conn.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def fetch_all(
        self,
        sql: str,
        params: Sequence[Any] = (),
    ) -> list[dict[str, Any]]:
        """
        Execute SQL and return all rows as list of dicts.

        Args:
            sql: SQL query
            params: Query parameters

        Returns:
            List of rows as dicts
        """
        with self.pool.connection() as conn, conn.cursor() as cursor:
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    def fetch_value(
        self,
        sql: str,
        params: Sequence[Any] = (),
    ) -> Any:
        """
        Execute SQL and return the first column of the first row.

        Args:
            sql: SQL query
            params: Query parameters

        Returns:
            First column value, or None if no rows
        """
        row = self.fetch_one(sql, params)
        if row is None:
            return None
        return next(iter(row.values()))

    # ── Insert / Update / Delete ──────────────────────────────

    def insert(
        self,
        table: str,
        values: dict[str, Any],
        returning: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Insert a row and optionally return the inserted record.

        Args:
            table: Table name
            values: Dict of column names to values
            returning: Column(s) to return (e.g. "id" or "*")

        Returns:
            Inserted row if returning is specified, else None
        """
        cols = ", ".join(values.keys())
        placeholders = ", ".join(["%s"] * len(values))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        if returning:
            sql += f" RETURNING {returning}"

        with self.transaction() as cursor:
            cursor.execute(sql, list(values.values()))
            if returning:
                return dict(cursor.fetchone())
        return None

    def update(
        self,
        table: str,
        values: dict[str, Any],
        where: str,
        params: Sequence[Any] = (),
    ) -> int:
        """
        Update rows matching a condition.

        Args:
            table: Table name
            values: Dict of column names to new values
            where: WHERE clause (e.g. "id = %s")
            params: Parameters for WHERE clause

        Returns:
            Number of rows updated
        """
        set_clause = ", ".join([f"{k} = %s" for k in values.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"

        with self.transaction() as cursor:
            cursor.execute(sql, list(values.values()) + list(params))
            return cursor.rowcount

    def delete(
        self,
        table: str,
        where: str,
        params: Sequence[Any] = (),
    ) -> int:
        """
        Delete rows matching a condition.

        Args:
            table: Table name
            where: WHERE clause (e.g. "id = %s")
            params: Parameters for WHERE clause

        Returns:
            Number of rows deleted
        """
        sql = f"DELETE FROM {table} WHERE {where}"

        with self.transaction() as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount

    # ── Schema migrations ─────────────────────────────────────

    def migrate(self, migrations: Sequence[str]) -> None:
        """
        Execute schema migrations. Each migration is a separate
        SQL statement.

        Args:
            migrations: List of SQL statements to execute
        """
        with self.transaction() as cursor:
            for migration in migrations:
                logger.debug("Executing migration: %s", migration[:100])
                cursor.execute(migration)
        logger.info("Applied %d migrations", len(migrations))

    def initialize_postgres_schema(self) -> "PostgreSQLClient":
        """Create the canonical Cerebro PostgreSQL schema."""
        from app.repository.note_repository import DEFAULT_SCHEMA_MIGRATIONS as migrations
        self.migrate(migrations)
        return self

"""Cerebro FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.logging_config import setup_logging
from app.router import review
from app.router import search
from app.client.watcher.observer import VaultObserver
from app.service.obsidian_service import ObsidianService
from app.repository.note_repository import NoteRepository

logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing PostgreSQL schema on application startup...")
    repo = NoteRepository()
    logger.info("PostgreSQL schema initialization complete.")

    logger.info("Starting VaultObserver for automated Obsidian note tracking...")
    vault_observer = None
    try:
        obsidian_service = ObsidianService()
        if obsidian_service.note_repo.db is not repo.db:
            obsidian_service.note_repo.db.close()
        obsidian_service.note_repo = repo
        vault_observer = VaultObserver(
            on_created_callback=obsidian_service.handle_note_created,
            on_modified_callback=obsidian_service.handle_note_modified,
            on_deleted_callback=obsidian_service.handle_note_deleted,
        )
        vault_observer.start()
        logger.info("Vault observer started successfully")
        try:
            obsidian_service.sync_vault()
        except Exception as e:
            logger.exception("Initial vault reconciliation failed: %s", e)
    except Exception as e:
        logger.exception("Failed to start required Vault observer: %s", e)
        repo.db.close()
        raise

    yield

    if vault_observer:
        logger.info("Stopping Vault observer...")
        try:
            vault_observer.stop()
            logger.info("Vault observer stopped successfully.")
        except Exception as e:
            logger.error(f"Error stopping Vault observer: {e}")
    repo.db.close()


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="Cerebro API",
        version="0.1.0",
        description=(
            "PostgreSQL + Obsidian + Ollama endpoints for active-recall review. "
            "Use /docs for Swagger UI."
        ),
        lifespan=lifespan,
    )

    app.include_router(review.router)
    app.include_router(search.router)

    @app.get("/", tags=["health"])
    def root() -> dict[str, str]:
        return {
            "service": "cerebro-api",
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "cerebro-api"}

    return app


app = create_app()


def main() -> None:
    import os
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

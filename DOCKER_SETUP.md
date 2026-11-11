# Docker deployment

Cerebro expects an existing PostgreSQL server on the Docker host, published on port 5432. Compose does not create or manage that database container. Create a database and user for Cerebro, then grant that user permission to create and alter the application tables.

1. Copy `.env.example` to `.env`.
2. Set `OBSIDIAN_VAULT_PATH` to the absolute host path of the vault.
3. Set the PostgreSQL credentials, `TELEGRAM_BOT_TOKEN`, and `GEMINI_API_KEY` if voice answers are required.
4. Ensure Ollama is reachable at `OLLAMA_BASE_URL` and has the configured chat and embedding models.
5. Start Cerebro with `docker compose up --build -d`.

Compose builds one `cerebro:latest` image and runs one `cerebro` container. The container starts the API, waits for its health endpoint, then starts Telegram polling. Both processes share the same environment and PostgreSQL connection settings. The API initializes the schema, indexes existing notes, and watches `/vault` for Markdown changes. PostgreSQL and Ollama are reached through `host.docker.internal`; Compose adds the host gateway mapping for Linux.

Useful commands:

```sh
docker compose ps
docker compose logs -f cerebro
curl http://localhost:8000/health
curl 'http://localhost:8000/search?q=your%20topic'
docker compose down
```

The vault is mounted read-only. PostgreSQL stores note metadata, section content and vectors, generated questions, Telegram users, answers, session overviews, and review history. See [README.md](README.md) for the schema and review behavior.

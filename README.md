# Cerebro

Cerebro indexes an Obsidian Markdown vault into PostgreSQL, embeds each section through Ollama, and runs adaptive active-recall reviews in Telegram.

## Architecture

- The FastAPI service initializes the PostgreSQL schema, reconciles existing vault notes, and watches the mounted vault for changes.
- Notes are split by Markdown heading hierarchy. Sections, source paths, review state, and embedding arrays are stored in PostgreSQL. Semantic search ranks stored section embeddings by cosine similarity.
- The Telegram service loads due sections, generates and persists MCQ, MSQ, and short-answer questions, evaluates answers, and records session summaries and feedback.
- Weak sessions are scheduled for the next day. Satisfied sessions advance the section through the configured 1, 3, 7, 14, 30, 60, and 120 day stages.
- Voice answers are downloaded from Telegram as OGG bytes and sent directly to Gemini multimodal input. Configure `GEMINI_API_KEY` to enable voice evaluation.

## Run with Docker Compose

The PostgreSQL server must already be running on the host and published on port 5432. Create `.env` from `.env.example`, set the vault path, database credentials, Telegram token, and LLM settings, then start the single Cerebro container:

```sh
cp .env.example .env
# Edit .env before starting
docker compose up --build -d
```

Compose builds one `cerebro:latest` image and runs one `cerebro` container. Inside it, the API starts first and the Telegram bot starts after the API is healthy. The API listens on `http://localhost:8000`; its health endpoint is `/health` and API docs are at `/docs`. The Telegram bot uses long polling and needs no inbound port. Stop Cerebro with `docker compose down`.

Docker Desktop and current Docker Engine setups resolve `host.docker.internal` to the host. Set `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DATABASE` to credentials for the existing PostgreSQL instance. The database user needs permission to create tables and indexes in the selected database. Set `OLLAMA_BASE_URL` to an Ollama endpoint reachable from the containers, and ensure the configured chat and embedding models are available there.

## Configuration

See [.env.example](.env.example). The main settings are:

- `OBSIDIAN_VAULT_PATH`: absolute host path mounted read-only at `/vault`.
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DATABASE`: existing host PostgreSQL credentials.
- `OLLAMA_BASE_URL`, `OLLAMA_CHAT_MODEL`, `EMBEDDING_MODEL`: question generation and embeddings.
- `TELEGRAM_BOT_TOKEN`: bot token. `/start` registers a chat for reminders.
- `TELEGRAM_ALLOWED_USERS`: optional comma-separated Telegram user IDs. Empty means any Telegram user can access the bot.
- `GEMINI_API_KEY`: required for direct OGG audio evaluation. `GEMINI_CHAT_MODEL` selects its multimodal model.

## Review behavior

Use `/topics` to select a due section. MCQ and MSQ are validated against their stored keys. Typed and voice short answers are evaluated against the reference answer by the configured LLM. At session end Cerebro stores an overview and the evaluation history. Satisfied sessions advance to the next interval; sessions with any unsatisfied answer return tomorrow.

## Data model

Schema initialization creates `notes`, `note_sections`, `generated_questions`, `review_sessions`, `review_answers`, `review_history`, and `telegram_users`. Vectors are stored as PostgreSQL `REAL[]` values with their model name and dimensions. Schema changes are applied on service startup.

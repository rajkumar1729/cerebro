"""Semantic search over indexed Markdown sections."""
from fastapi import APIRouter, HTTPException, Query

from app.client.embedding.ollama_embedder import OllamaEmbeddingClient
from app.repository.note_repository import NoteRepository

router = APIRouter(prefix="/search", tags=["Semantic search"])


@router.get("")
def search_sections(q: str = Query(min_length=2), limit: int = Query(default=10, ge=1, le=50)) -> list[dict]:
    repo = NoteRepository()
    try:
        embedding = OllamaEmbeddingClient().get_query_embedding(q)
        results = repo.search_similar_sections(embedding, limit=limit)
        for row in results:
            row.pop("embedding", None)
        return results
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Semantic search unavailable: {exc}") from exc
    finally:
        repo.db.close()

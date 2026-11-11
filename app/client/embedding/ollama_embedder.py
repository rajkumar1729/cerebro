"""
OllamaEmbeddingClient — Client for generating embeddings via Ollama.

Wraps the Ollama ``/api/embed`` REST endpoint to produce vector
embeddings for text using locally-running models like
``nomic-embed-text``.

Supports single and batch embedding, with configurable base URL
and model selection.
"""

from __future__ import annotations

import math
from typing import List, Dict, Any
from ollama import Client

from app.config import AppSettings
from app.logging_config import setup_logging

settings = AppSettings()
logger = setup_logging()

class OllamaEmbeddingClient:
    """
    Client for generating embeddings locally using Ollama.
    Optimized for nomic-embed-text with automatic prefixing and batching.
    """
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
        batch_size: int = 32
    ):
        self.base_url = base_url or settings.llm.ollama_base_url
        self.model = model or settings.llm.embedding_model
        self.batch_size = batch_size

        self.client = Client(host=self.base_url, timeout=timeout)
        self._is_nomic = "nomic" in self.model.lower()

    @staticmethod
    def _first_embedding(response: Any) -> List[float]:
        embeddings = response.get("embeddings") if isinstance(response, dict) else response.embeddings
        if not embeddings:
            raise RuntimeError("Ollama returned no embeddings")
        return list(embeddings[0])

    def _format_input(self, text: str, is_query: bool = False) -> str:
        """Applies task-specific prefixes if using nomic-embed-text."""
        if not self._is_nomic:
            return text
        prefix = "search_query: " if is_query else "search_document: "
        return f"{prefix}{text.strip()}"

    def get_document_embedding(self, text: str) -> List[float]:
        """Generate an embedding for a single document or note section."""
        formatted_text = self._format_input(text, is_query=False)
        try:
            response = self.client.embed(model=self.model, input=formatted_text)
            return self._first_embedding(response)
        except Exception as e:
            logger.error(f"Error generating document embedding: {e}")
            raise

    def get_query_embedding(self, query: str) -> List[float]:
        """Generate an embedding for a search/RAG query."""
        formatted_query = self._format_input(query, is_query=True)
        try:
            response = self.client.embed(model=self.model, input=formatted_query)
            return self._first_embedding(response)
        except Exception as e:
            logger.error(f"Error generating query embedding: {e}")
            raise

    def embedding_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """Compute cosine similarity between two vector embeddings."""
        if not embedding1 or not embedding2 or len(embedding1) != len(embedding2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        magnitude1 = math.sqrt(sum(a * a for a in embedding1))
        magnitude2 = math.sqrt(sum(b * b for b in embedding2))

        if magnitude1 == 0.0 or magnitude2 == 0.0:
            return 0.0

        similarity = dot_product / (magnitude1 * magnitude2)
        # Clamp to [-1.0, 1.0] range to correct float precision errors
        return max(-1.0, min(1.0, similarity))

    def evaluate_subtopic_similarity(self, old_embedding: List[float], new_embedding: List[float]) -> Dict[str, Any]:
        """
        Evaluates subtopic similarity score and returns stage demotion recommendations.

        Returns:
            {
                "similarity": float,
                "demotion_steps": int,
                "action": "KEEP" | "DEMOTE_1" | "DEMOTE_2" | "RESET"
            }
        """
        sim = self.embedding_similarity(old_embedding, new_embedding)

        if sim >= 0.85:
            return {"similarity": sim, "demotion_steps": 0, "action": "KEEP"}
        elif sim >= 0.70:
            return {"similarity": sim, "demotion_steps": 1, "action": "DEMOTE_1"}
        elif sim >= 0.55:
            return {"similarity": sim, "demotion_steps": 2, "action": "DEMOTE_2"}
        else:
            return {"similarity": sim, "demotion_steps": 999, "action": "RESET"}

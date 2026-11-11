# Qdrant Vector Database — Setup & Usage Guide

Qdrant is a high-performance vector database for similarity search. Store embeddings alongside metadata (payloads), then search by semantic similarity. Perfect for RAG, recommendation, and knowledge retrieval.

---

## 1. Installation Options

### Option A — Docker (Recommended for Dev & Production)

```bash
docker run -p 6333:6333 -p 6334:6334 \
    -v $(pwd)/qdrant_storage:/qdrant/storage:z \
    qdrant/qdrant
```

| Port | Purpose |
| :--- | :--- |
| `6333` | REST API + Web Dashboard |
| `6334` | gRPC API (faster, used by client) |

Once running, open the dashboard at **http://localhost:6333/dashboard**.

#### Docker Compose (persistent setup)

```yaml
# docker-compose.yml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./qdrant_storage:/qdrant/storage
    restart: unless-stopped
```

```bash
docker compose up -d
```

### Option B — Local Mode (No Server, No Docker)

The Python client can run Qdrant **embedded** — no server needed. Good for prototyping and tests.

```bash
pip install qdrant-client
```

```python
from qdrant_client import QdrantClient

# In-memory (data lost on exit) — great for tests
client = QdrantClient(":memory:")

# On-disk (persisted to a folder) — no server needed
client = QdrantClient(path="./qdrant_local")
```

> ⚠️ Local mode is **not production-grade** — no concurrency, no gRPC, different storage format from server mode. Use Docker for anything real.

### Option C — Qdrant Cloud (Managed)

1. Sign up at [cloud.qdrant.io](https://cloud.qdrant.io)
2. Create a cluster → get a URL and API key
3. Connect:

```python
client = QdrantClient(
    url="https://your-cluster.cloud.qdrant.io:6333",
    api_key="your-api-key",
)
```

---

## 2. Python Client Setup

```bash
pip install qdrant-client
```

### Connect

```python
from qdrant_client import QdrantClient, models

# To Docker / server
client = QdrantClient(url="http://localhost:6333")

# To in-memory (testing)
client = QdrantClient(":memory:")

# To local disk (no server)
client = QdrantClient(path="./qdrant_local")
```

---

## 3. Core Concepts

| Concept | What it is |
| :--- | :--- |
| **Collection** | A named group of vectors (like a table) |
| **Point** | A single record: `id` + `vector` + `payload` |
| **Vector** | The embedding (list of floats) |
| **Payload** | JSON metadata attached to a point (filterable) |
| **Distance** | Similarity metric: `COSINE`, `EUCLID`, or `DOT` |

---

## 4. Full CRUD Walkthrough

### Create a Collection

```python
client.create_collection(
    collection_name="notes",
    vectors_config=models.VectorParams(
        size=384,                        # must match your embedding model's output dim
        distance=models.Distance.COSINE, # most common for text embeddings
    ),
)
```

Common embedding dimensions:

| Model | Dimensions |
| :--- | :--- |
| `all-MiniLM-L6-v2` | 384 |
| `text-embedding-3-small` (OpenAI) | 1536 |
| `nomic-embed-text` (Ollama) | 768 |
| `mxbai-embed-large` (Ollama) | 1024 |

### Upsert Points (Insert or Update)

```python
client.upsert(
    collection_name="notes",
    points=[
        models.PointStruct(
            id=1,
            vector=[0.1, 0.2, 0.3, ...],  # your embedding
            payload={
                "title": "Neural Networks",
                "source": "lecture-notes/week3.md",
                "tags": ["ml", "deep-learning"],
                "created_at": "2025-01-15",
            },
        ),
        models.PointStruct(
            id=2,
            vector=[0.4, 0.5, 0.6, ...],
            payload={
                "title": "Backpropagation",
                "source": "lecture-notes/week4.md",
                "tags": ["ml", "optimization"],
                "created_at": "2025-01-22",
            },
        ),
    ],
)
```

### Search (Nearest Neighbors)

```python
results = client.query_points(
    collection_name="notes",
    query=[0.11, 0.21, 0.31, ...],  # query embedding
    limit=5,
)

for point in results.points:
    print(f"ID: {point.id}, Score: {point.score}")
    print(f"  Title: {point.payload['title']}")
    print(f"  Source: {point.payload['source']}")
```

### Search with Payload Filters

Combine vector similarity with structured filtering:

```python
results = client.query_points(
    collection_name="notes",
    query=[0.11, 0.21, 0.31, ...],
    query_filter=models.Filter(
        must=[
            models.FieldCondition(
                key="tags",
                match=models.MatchValue(value="ml"),
            ),
        ],
    ),
    limit=5,
)
```

#### More filter examples

```python
# Match multiple values (OR)
models.FieldCondition(
    key="tags",
    match=models.MatchAny(any=["ml", "optimization"]),
)

# Range filter (dates, numbers)
models.FieldCondition(
    key="created_at",
    range=models.Range(gte="2025-01-01", lte="2025-12-31"),
)

# Exclude specific values
models.Filter(
    must_not=[
        models.FieldCondition(
            key="source",
            match=models.MatchValue(value="archive/old.md"),
        ),
    ],
)
```

### Retrieve a Point by ID

```python
points = client.retrieve(
    collection_name="notes",
    ids=[1, 2],
    with_payload=True,
    with_vectors=False,  # set True if you need the raw embedding
)
```

### Delete Points

```python
# By ID
client.delete(
    collection_name="notes",
    points_selector=models.PointIdsList(points=[1, 2]),
)

# By filter (delete all with a specific tag)
client.delete(
    collection_name="notes",
    points_selector=models.FilterSelector(
        filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="tags",
                    match=models.MatchValue(value="deprecated"),
                ),
            ],
        ),
    ),
)
```

### Delete a Collection

```python
client.delete_collection(collection_name="notes")
```

---

## 5. Generating Embeddings

Qdrant stores vectors — you need to generate them yourself. Here are the common approaches.

### Using Sentence Transformers (Local, Free)

```bash
pip install sentence-transformers
```

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")  # 384 dimensions

texts = ["Neural networks are cool", "Backpropagation explained"]
embeddings = model.encode(texts).tolist()

# embeddings[0] → [0.012, -0.034, ...] (384 floats)
```

### Using Ollama (Local, Free)

```bash
ollama pull nomic-embed-text
```

```python
import requests

def embed_with_ollama(text: str, model: str = "nomic-embed-text") -> list[float]:
    response = requests.post(
        "http://localhost:11434/api/embed",
        json={"model": model, "input": text},
    )
    return response.json()["embeddings"][0]

vector = embed_with_ollama("Neural networks are cool")
# → list of 768 floats
```

### Using OpenAI

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI()

response = client.embeddings.create(
    model="text-embedding-3-small",
    input="Neural networks are cool",
)
vector = response.data[0].embedding
# → list of 1536 floats
```

---

## 6. Payload Indexes (Important for Performance)

Create indexes on payload fields you filter on **before** ingesting data:

```python
client.create_payload_index(
    collection_name="notes",
    field_name="tags",
    field_schema=models.PayloadSchemaType.KEYWORD,
)

client.create_payload_index(
    collection_name="notes",
    field_name="created_at",
    field_schema=models.PayloadSchemaType.DATETIME,
)

client.create_payload_index(
    collection_name="notes",
    field_name="source",
    field_schema=models.PayloadSchemaType.KEYWORD,
)
```

| Schema Type | Use for |
| :--- | :--- |
| `KEYWORD` | Exact match strings, tags, categories |
| `INTEGER` | Numeric IDs, counts |
| `FLOAT` | Scores, decimals |
| `DATETIME` | Date/time filtering and ranges |
| `TEXT` | Full-text search within payloads |
| `BOOL` | Boolean flags |

---

## 7. Collection Aliases

Use aliases for zero-downtime collection swaps (e.g. when re-embedding with a new model):

```python
# Point an alias to a collection
client.update_collection_aliases(
    change_aliases_operations=[
        models.CreateAliasOperation(
            create_alias=models.CreateAlias(
                collection_name="notes_v2",
                alias_name="notes",
            ),
        ),
    ],
)

# Now client.query_points(collection_name="notes", ...) hits notes_v2
```

---

## 8. Integration Pattern for Cerebro

A reusable wrapper that pairs embedding generation with Qdrant storage:

```python
import uuid
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer


class VectorStore:
    def __init__(
        self,
        collection_name: str = "notes",
        embedding_model: str = "all-MiniLM-L6-v2",
        qdrant_url: str = "http://localhost:6333",
    ):
        self.collection_name = collection_name
        self.client = QdrantClient(url=qdrant_url)
        self.model = SentenceTransformer(embedding_model)
        self.vector_size = self.model.get_sentence_embedding_dimension()
        self._ensure_collection()

    def _ensure_collection(self):
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            # Index common filter fields
            for field, schema in [
                ("source", models.PayloadSchemaType.KEYWORD),
                ("tags", models.PayloadSchemaType.KEYWORD),
            ]:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=schema,
                )

    def add(self, text: str, metadata: dict | None = None) -> str:
        """Embed and store a single text. Returns the point ID."""
        point_id = str(uuid.uuid4())
        vector = self.model.encode(text).tolist()
        payload = {"text": text, **(metadata or {})}

        self.client.upsert(
            collection_name=self.collection_name,
            points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
        )
        return point_id

    def add_batch(self, texts: list[str], metadatas: list[dict] | None = None) -> list[str]:
        """Embed and store multiple texts."""
        metadatas = metadatas or [{}] * len(texts)
        vectors = self.model.encode(texts).tolist()
        ids = [str(uuid.uuid4()) for _ in texts]

        points = [
            models.PointStruct(
                id=pid,
                vector=vec,
                payload={"text": txt, **meta},
            )
            for pid, vec, txt, meta in zip(ids, vectors, texts, metadatas)
        ]

        self.client.upsert(collection_name=self.collection_name, points=points)
        return ids

    def search(
        self,
        query: str,
        limit: int = 5,
        filter_tags: list[str] | None = None,
    ) -> list[dict]:
        """Semantic search. Returns list of {id, score, payload}."""
        query_vector = self.model.encode(query).tolist()

        query_filter = None
        if filter_tags:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="tags",
                        match=models.MatchAny(any=filter_tags),
                    ),
                ],
            )

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
        )

        return [
            {"id": p.id, "score": p.score, "payload": p.payload}
            for p in results.points
        ]

    def delete(self, point_ids: list[str]):
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=point_ids),
        )


# Usage
if __name__ == "__main__":
    store = VectorStore()

    # Add notes
    store.add("Neural networks learn through backpropagation", {"tags": ["ml"], "source": "week3.md"})
    store.add("Gradient descent minimizes the loss function", {"tags": ["ml", "optimization"], "source": "week4.md"})
    store.add("Python decorators wrap functions", {"tags": ["python"], "source": "misc.md"})

    # Search
    results = store.search("how do neural nets learn?", limit=2)
    for r in results:
        print(f"[{r['score']:.3f}] {r['payload']['text']}")

    # Search with filter
    results = store.search("optimization", filter_tags=["ml"])
    for r in results:
        print(f"[{r['score']:.3f}] {r['payload']['text']}")
```

---

## 9. Useful API Endpoints (REST)

All at `http://localhost:6333`:

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/collections` | GET | List all collections |
| `/collections/{name}` | GET | Collection info (point count, config) |
| `/collections/{name}` | DELETE | Delete a collection |
| `/collections/{name}/points/search` | POST | Vector similarity search |
| `/collections/{name}/points/scroll` | POST | Paginate through all points |
| `/collections/{name}/points` | PUT | Upsert points |
| `/dashboard` | GET | Web UI |

```bash
# Quick health check
curl http://localhost:6333/healthz

# List collections
curl http://localhost:6333/collections

# Get collection info
curl http://localhost:6333/collections/notes
```

---

## 10. Performance Tips

| Tip | Details |
| :--- | :--- |
| **Index payload fields first** | Create indexes before bulk insert, not after |
| **Use gRPC** | The Python client uses gRPC on port 6334 automatically — faster than REST |
| **Batch upserts** | Insert in batches of 100–500 points, not one at a time |
| **Quantization** | For large datasets, enable scalar quantization to cut memory ~4x with minimal recall loss |
| **Store source text in payload** | Always keep the original text — lets you re-embed if you switch models |
| **Use `with_vectors=False`** | When retrieving points, skip vectors if you don't need them |

### Enable Quantization

```python
client.update_collection(
    collection_name="notes",
    quantization_config=models.ScalarQuantization(
        scalar=models.ScalarQuantizationConfig(
            type=models.ScalarType.INT8,
            always_ram=True,
        ),
    ),
)
```

---

## 11. Backup & Restore

### Create a Snapshot

```bash
curl -X POST "http://localhost:6333/collections/notes/snapshots"
```

### List Snapshots

```bash
curl "http://localhost:6333/collections/notes/snapshots"
```

### Restore from Snapshot

```bash
curl -X PUT "http://localhost:6333/collections/notes/snapshots/recover" \
  -H "Content-Type: application/json" \
  -d '{"location": "http://localhost:6333/collections/notes/snapshots/<snapshot-name>"}'
```

---

## TL;DR

```
1. docker run -p 6333:6333 qdrant/qdrant      ← start server
2. pip install qdrant-client sentence-transformers
3. Create collection (set size to match your embedding model)
4. Embed text → upsert as points with payload metadata
5. Search by embedding → get ranked results
6. Index payload fields you filter on
7. Store source text in payload for future re-embedding
```

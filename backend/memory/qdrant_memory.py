import os
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from backend.utils.logger import log_action

COLLECTION_NAME = "dexter_memory"
EMBEDDING_MODEL_NAME = os.getenv("DEXTER_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
MEMORY_LOCAL_ONLY = os.getenv("DEXTER_MEMORY_LOCAL_ONLY", "true").lower() in {
    "1",
    "true",
    "yes",
}
MEMORY_ENABLED = os.getenv("DEXTER_MEMORY_ENABLED", "false").lower() not in {
    "0",
    "false",
    "no",
}

_client = None
_embedding_model = None
_memory_error = None


def get_client():
    global _client

    if _client is None:
        _client = QdrantClient(path="./qdrant_storage")

    return _client


def get_embedding_model():
    global _embedding_model, _memory_error

    if not MEMORY_ENABLED:
        return None

    if _embedding_model is not None:
        return _embedding_model

    if _memory_error is not None:
        return None

    try:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_NAME,
            local_files_only=MEMORY_LOCAL_ONLY,
        )
        return _embedding_model
    except Exception as e:
        _memory_error = str(e)
        log_action(
            "memory_embedding_unavailable",
            {
                "model": EMBEDDING_MODEL_NAME,
                "local_only": MEMORY_LOCAL_ONLY,
                "error": _memory_error,
            },
        )
        return None


def ensure_collection():
    client = get_client()
    collections = client.get_collections().collections
    names = [collection.name for collection in collections]

    if COLLECTION_NAME not in names:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )


def store_memory(text: str, metadata: dict | None = None):
    if not MEMORY_ENABLED:
        return {"ok": False, "error": "Memory disabled"}

    model = get_embedding_model()

    if model is None:
        return {"ok": False, "error": _memory_error or "Memory embedding unavailable"}

    ensure_collection()

    payload = metadata or {}
    payload["text"] = text

    vector = model.encode(text).tolist()

    point = PointStruct(
        id=str(uuid4()),
        vector=vector,
        payload=payload,
    )

    get_client().upsert(collection_name=COLLECTION_NAME, points=[point])
    return {"ok": True}


def query_memory(query_text: str, top_k: int = 3):
    if not MEMORY_ENABLED:
        return []

    model = get_embedding_model()

    if model is None:
        return []

    ensure_collection()

    vector = model.encode(query_text).tolist()

    results = get_client().query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=top_k,
    )

    return [
        {
            "text": point.payload.get("text"),
            "score": point.score,
        }
        for point in results.points
    ]

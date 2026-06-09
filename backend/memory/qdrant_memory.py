from uuid import uuid4
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from sentence_transformers import SentenceTransformer

COLLECTION_NAME = "dexter_memory"

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
client = QdrantClient(path="./qdrant_storage")


def ensure_collection():
    collections = client.get_collections().collections
    names = [collection.name for collection in collections]

    if COLLECTION_NAME not in names:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )


def store_memory(text: str, metadata: dict | None = None):
    ensure_collection()

    payload = metadata or {}
    payload["text"] = text

    vector = embedding_model.encode(text).tolist()

    point = PointStruct(
        id=str(uuid4()),
        vector=vector,
        payload=payload,
    )

    client.upsert(collection_name=COLLECTION_NAME, points=[point])


def query_memory(query_text: str, top_k: int = 3):
    ensure_collection()

    vector = embedding_model.encode(query_text).tolist()

    results = client.query_points(
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

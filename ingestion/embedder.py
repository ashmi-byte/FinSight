import sqlite3
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from langchain_openai import OpenAIEmbeddings

EMBEDDING_MODEL = "text-embedding-3-large"
VECTOR_DIM = 3072
BATCH_SIZE = 64


def embed_and_store(
    parents: list[dict],
    children: list[dict],
    collection_name: str,
    db_path: str,
    qdrant_url: str = "http://localhost:6333",
):
    """
    Store parent chunks in SQLite (for context reconstruction)
    and embed child chunks into Qdrant (for semantic search).
    """
    _store_parents_sqlite(parents, db_path)
    _store_children_qdrant(children, collection_name, qdrant_url)


def _store_parents_sqlite(parents: list[dict], db_path: str):
    if not parents:
        return
    conn = sqlite3.connect(db_path)
    conn.executemany(
        """INSERT OR IGNORE INTO parent_chunks
           (id, report_id, section, subsection, text, page, position)
           VALUES (:id, :report_id, :section, :subsection, :text, :page, :position)""",
        parents,
    )
    conn.commit()
    conn.close()


def _store_children_qdrant(children: list[dict], collection_name: str, qdrant_url: str):
    if not children:
        return

    client = QdrantClient(url=qdrant_url, check_compatibility=False)
    embeddings_model = OpenAIEmbeddings(model=EMBEDDING_MODEL)

    existing = [c.name for c in client.get_collections().collections]
    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )

    for i in range(0, len(children), BATCH_SIZE):
        batch = children[i : i + BATCH_SIZE]
        vectors = embeddings_model.embed_documents([c["text"] for c in batch])
        points = [
            PointStruct(
                id=c["id"],
                vector=vec,
                payload={
                    "text": c["text"],
                    "parent_id": c["parent_id"],
                    "report_id": c["report_id"],
                    "section": c.get("section"),
                    "subsection": c.get("subsection"),
                    "page": c.get("page"),
                    # backward-compatible fields for existing retrieval code
                    "company": c["report_id"].rsplit("_", 1)[0],
                    "year": _parse_year(c["report_id"]),
                },
            )
            for c, vec in zip(batch, vectors)
        ]
        client.upsert(collection_name=collection_name, points=points)


def _parse_year(report_id: str) -> int | None:
    part = report_id.rsplit("_", 1)[-1]
    return int(part) if part.isdigit() else None

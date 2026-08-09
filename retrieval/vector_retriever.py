import os
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from langchain_openai import OpenAIEmbeddings
from ingestion.db_schema import get_parent

DB_PATH = os.getenv("SQLITE_PATH", "data/financials.db")

client = QdrantClient(url="http://localhost:6333", check_compatibility=False)
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

COLLECTION = "financial_reports"


def vector_search(
    query: str,
    company: str = None,
    year: int = None,
    report_id: str = None,
    top_k: int = 5,
) -> list[dict]:
    """
    Search child chunks by semantic similarity, then return parent chunk text
    for richer context. Supports filtering by report_id (precise) or company/year.
    """
    conditions = []
    if report_id:
        conditions.append(FieldCondition(key="report_id", match=MatchValue(value=report_id)))
    else:
        if company:
            conditions.append(FieldCondition(key="company", match=MatchValue(value=company.lower())))
        if year:
            conditions.append(FieldCondition(key="year", match=MatchValue(value=year)))

    vector = embeddings.embed_query(query)
    response = client.query_points(
        collection_name=COLLECTION,
        query=vector,
        limit=top_k,
        query_filter=Filter(must=conditions) if conditions else None,
        with_payload=True,
    )

    seen_parents: set[str] = set()
    results = []

    for r in response.points:
        parent_id = r.payload.get("parent_id")

        # Deduplicate: multiple children from same parent → return parent once
        if parent_id and parent_id in seen_parents:
            continue

        parent = get_parent(parent_id, DB_PATH) if parent_id else None

        results.append({
            "text":      parent["text"] if parent else r.payload.get("text", ""),
            "score":     r.score,
            "company":   r.payload.get("company"),
            "year":      r.payload.get("year"),
            "page":      parent["page"] if parent else r.payload.get("page"),
            "section":   parent["section"] if parent else r.payload.get("section"),
            "source":    r.payload.get("report_id", r.payload.get("source", "")),
            "parent_id": parent_id,
        })

        if parent_id:
            seen_parents.add(parent_id)

    return results

"""
Unified retrieval interface for the LangGraph agent.
The agent decides which retriever(s) to call — this file just wraps them cleanly.
"""
from retrieval.vector_retriever import vector_search
from retrieval.sql_retriever import sql_search


def retrieve(
    query: str,
    mode: str = "both",          # "vector" | "sql" | "both"
    company: str = None,
    year: int = None,
    top_k: int = 5,
) -> dict:
    """
    mode="vector"  — semantic search only (narrative, strategy, context)
    mode="sql"     — structured lookup only (exact numbers, comparisons)
    mode="both"    — run both and merge (comparison queries)
    """
    results = {"vector": [], "sql": None}

    if mode in ("vector", "both"):
        results["vector"] = vector_search(query, company=company, year=year, top_k=top_k)

    if mode in ("sql", "both"):
        results["sql"] = sql_search(query)

    return results


def format_for_context(results: dict) -> str:
    """Flatten retrieval results into a single context string for the LLM."""
    parts = []

    for doc in results.get("vector", []):
        parts.append(f"[Source: {doc['company']} {doc['year']} p.{doc['page']}]\n{doc['text']}")

    sql_result = results.get("sql")
    if sql_result and sql_result["results"]:
        parts.append(f"[Financial Data]\n{sql_result['results']}")
    elif sql_result and sql_result["error"]:
        parts.append(f"[SQL Error: {sql_result['error']}]")

    return "\n\n---\n\n".join(parts)

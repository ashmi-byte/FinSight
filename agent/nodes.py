import os
import json
from typing import Literal
from langchain_openai import ChatOpenAI
from retrieval.vector_retriever import vector_search
from retrieval.sql_retriever import sql_search
from ingestion.db_schema import get_available_reports
from agent.prompts import (
    CLASSIFY_PROMPT, DECOMPOSE_PROMPT, REWRITE_PROMPT, GENERATE_PROMPT
)

DB_PATH = os.getenv("SQLITE_PATH", "data/financials.db")

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

RELEVANCE_THRESHOLD = 0.55
MAX_RETRIES = 1  # max 1 rewrite per sub-question


# ── nodes ─────────────────────────────────────────────────────────────────────

def classify_query(state: dict) -> dict:
    prompt = CLASSIFY_PROMPT.format(question=state["question"])
    raw = llm.invoke(prompt).content.strip()
    try:
        parsed = json.loads(raw)
        query_type = parsed.get("type", "simple")
        mode = parsed.get("mode", "sql")
        company = parsed.get("company")
        year_raw = parsed.get("year")
        year = int(year_raw) if isinstance(year_raw, int) else None
    except json.JSONDecodeError:
        query_type, mode, company, year = "simple", "sql", None, None

    if query_type not in ("simple", "multihop", "cross_document"):
        query_type = "simple"
    if mode not in ("sql", "vector"):
        mode = "sql"

    # For simple queries, build sub_questions directly from classify output
    sub_questions = []
    if query_type == "simple":
        sub_questions = [{
            "question": state["question"],
            "search_query": state["question"],
            "mode": mode,
            "company": company,
            "year": year,
            "report_ids": [],
            "vector_docs": [],
            "sql_results": [],
            "relevance_score": 0.0,
            "status": "pending",
            "retry_count": 0,
        }]

    return {**state, "query_type": query_type, "mode": mode, "sub_questions": sub_questions}


def decompose_query(state: dict) -> dict:
    prompt = DECOMPOSE_PROMPT.format(question=state["question"])
    raw = llm.invoke(prompt).content.strip()
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        items = [{"question": state["question"], "search_query": state["question"], "mode": "sql"}]

    sub_questions = [
        {
            "question": item.get("question", state["question"]),
            "search_query": item.get("search_query", item.get("question", state["question"])),
            "mode": item.get("mode", "sql") if item.get("mode") in ("sql", "vector") else "sql",
            "company": item.get("company") or None,
            "year": int(item["year"]) if isinstance(item.get("year"), int) else None,
            "report_ids": [],
            "vector_docs": [],
            "sql_results": [],
            "relevance_score": 0.0,
            "status": "pending",
            "retry_count": 0,
        }
        for item in items
    ]
    return {**state, "sub_questions": sub_questions}


def route_documents(state: dict) -> dict:
    available = get_available_reports(DB_PATH)

    # Build indexes for fast lookup
    by_company_year = {(r["company"], r["year"]): r["report_id"] for r in available}
    by_company: dict[str, list] = {}
    for r in available:
        by_company.setdefault(r["company"], []).append(r)
    for reports in by_company.values():
        reports.sort(key=lambda r: r["year"], reverse=True)  # newest first

    updated = []
    for sq in state["sub_questions"]:
        sq = dict(sq)
        company = sq.get("company")
        year = sq.get("year")

        report_ids = []
        if company:
            company = company.lower()
            if year:
                rid = by_company_year.get((company, int(year)))
                report_ids = [rid] if rid else [r["report_id"] for r in by_company.get(company, [])]
            else:
                report_ids = [r["report_id"] for r in by_company.get(company, [])]

        sq["report_ids"] = report_ids
        updated.append(sq)

    return {**state, "sub_questions": updated}


def retrieve(state: dict) -> dict:
    updated = []
    for sq in state["sub_questions"]:
        if sq["status"] in ("done", "best_effort"):
            updated.append(sq)
            continue

        sq = dict(sq)
        mode = sq["mode"]
        query = sq["search_query"]

        vector_docs = []
        sql_results = []

        company = sq.get("company")

        report_ids = sq.get("report_ids", [])

        if mode == "vector":
            vector_docs = _vector_search_scoped(query, report_ids, company, top_k=4)
        elif mode == "sql":
            result = sql_search(sq["search_query"])
            if result["results"]:
                sql_results.append({
                    "question": sq["question"],
                    "sql": result["sql"],
                    "data": result["results"],
                })
            else:
                # SQL returned no results or failed — fallback to vector and don't retry SQL
                vector_docs = _vector_search_scoped(query, report_ids, company, top_k=4)
                sq["mode"] = "vector"

        sq["vector_docs"] = vector_docs
        sq["sql_results"] = sql_results
        updated.append(sq)

    return {**state, "sub_questions": updated}


def evaluate_relevance(state: dict) -> dict:
    updated = []
    for sq in state["sub_questions"]:
        if sq["status"] in ("done", "best_effort"):
            updated.append(sq)
            continue

        sq = dict(sq)

        if sq["sql_results"] and _validate_sql(sq["sql_results"]):
            sq["relevance_score"] = 1.0
            sq["status"] = "done"
        elif sq["sql_results"] and not _validate_sql(sq["sql_results"]):
            # SQL returned rows but values are invalid — discard and fall through to vector
            sq["sql_results"] = []
            sq["relevance_score"] = 0.0
            if sq["retry_count"] >= MAX_RETRIES:
                sq["status"] = "best_effort"
            else:
                sq["status"] = "rewriting"
        elif sq["vector_docs"]:
            avg = sum(d.get("score", 0) for d in sq["vector_docs"]) / len(sq["vector_docs"])
            sq["relevance_score"] = avg
            if avg >= RELEVANCE_THRESHOLD:
                sq["status"] = "done"
            elif sq["retry_count"] >= MAX_RETRIES:
                sq["status"] = "best_effort"
            else:
                sq["status"] = "rewriting"
        else:
            sq["relevance_score"] = 0.0
            if sq["retry_count"] >= MAX_RETRIES:
                sq["status"] = "best_effort"
            else:
                sq["status"] = "rewriting"

        updated.append(sq)

    return {**state, "sub_questions": updated}


def rewrite_query(state: dict) -> dict:
    updated = []
    for sq in state["sub_questions"]:
        if sq["status"] != "rewriting":
            updated.append(sq)
            continue

        sq = dict(sq)
        failed_snippets = " | ".join(
            d["text"][:100] for d in sq["vector_docs"][:2]
        ) or "no results"

        prompt = REWRITE_PROMPT.format(
            question=sq["question"],
            search_query=sq["search_query"],
            failed_snippets=failed_snippets,
        )
        new_query = llm.invoke(prompt).content.strip()
        sq["search_query"] = new_query
        sq["retry_count"] = sq["retry_count"] + 1
        sq["status"] = "pending"
        sq["vector_docs"] = []
        sq["sql_results"] = []
        updated.append(sq)

    return {**state, "sub_questions": updated}


def generate_answer(state: dict) -> dict:
    context_parts = []

    for sq in state["sub_questions"]:
        header = f"### Sub-question: {sq['question']}"
        if sq["status"] == "best_effort":
            header += " [BEST EFFORT — limited information]"
        context_parts.append(header)

        if sq["sql_results"]:
            for r in sq["sql_results"]:
                context_parts.append(f"Financial Data:\n{r['data']}")

        if sq["vector_docs"]:
            for d in sq["vector_docs"]:
                label = f"[{d.get('company','?')} {d.get('year','?')} p.{d.get('page','?')}]"
                context_parts.append(f"{label}\n{d['text']}")

    context = "\n\n".join(context_parts)
    prompt = GENERATE_PROMPT.format(context=context, question=state["question"])
    answer = llm.invoke(prompt).content

    sources = list({
        f"{d.get('company')} {d.get('year')} p.{d.get('page')}"
        for sq in state["sub_questions"]
        for d in sq.get("vector_docs", [])
        if d.get("company")
    })

    return {**state, "final_answer": answer, "sources": sources}


# ── helpers ───────────────────────────────────────────────────────────────────

def _vector_search_scoped(query: str, report_ids: list, company: str, top_k: int = 4) -> list:
    if not report_ids:
        return vector_search(query, top_k=top_k, company=company)
    if len(report_ids) == 1:
        return vector_search(query, report_id=report_ids[0], top_k=top_k)
    per_k = max(2, top_k // len(report_ids))
    all_docs = []
    for rid in report_ids:
        all_docs.extend(vector_search(query, report_id=rid, top_k=per_k))
    return sorted(all_docs, key=lambda d: d.get("score", 0), reverse=True)[:top_k]


def _validate_sql(sql_results: list) -> bool:
    for r in sql_results:
        for row in r["data"]:
            numeric_values = [
                v for k, v in row.items()
                if k not in ("company", "ticker", "section", "period", "currency", "metric")
                and v is not None
                and isinstance(v, (int, float))
            ]
            if numeric_values:
                return True
    return False


# ── routing condition ─────────────────────────────────────────────────────────

def should_continue(state: dict) -> Literal["rewrite", "generate"]:
    statuses = {sq["status"] for sq in state["sub_questions"]}
    if "rewriting" in statuses:
        return "rewrite"
    return "generate"

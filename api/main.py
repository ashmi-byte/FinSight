import os
import sys
import json
import asyncio
import shutil
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.graph import app_graph, AgentState
from ingestion.db_schema import init_db, register_company, register_report, is_already_ingested
from ingestion.pdf_parser import parse_pdf
from ingestion.text_chunker import chunk_documents_hierarchical
from ingestion.embedder import embed_and_store
from ingestion.financial_data_fetcher import fetch_and_store, COMPANY_TICKER_MAP

RAW_DIR = Path("data/raw")
DB_PATH = "data/financials.db"
COLLECTION = "financial_reports"

app = FastAPI(title="Financial RAG")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── models ────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str


# ── SSE streaming query ───────────────────────────────────────────────────────

@app.post("/query")
async def query(request: QueryRequest):
    async def event_stream():
        try:
            async for event in app_graph.astream_events(
                {"question": request.question},
                version="v2",
            ):
                kind = event["event"]
                name = event.get("name", "")

                if kind == "on_chain_end" and name == "classify":
                    data = event["data"]["output"]
                    yield _sse("classify", {
                        "query_type": data.get("query_type"),
                        "mode": data.get("mode"),
                    })

                elif kind == "on_chain_end" and name == "decompose":
                    data = event["data"]["output"]
                    sqs = data.get("sub_questions", [])
                    yield _sse("decompose", {
                        "sub_questions": [
                            {"question": sq["question"], "mode": sq["mode"]}
                            for sq in sqs
                        ]
                    })

                elif kind == "on_chain_end" and name == "retrieve":
                    data = event["data"]["output"]
                    sqs = data.get("sub_questions", [])
                    yield _sse("retrieve", {
                        "sub_questions": [
                            {
                                "question": sq["question"],
                                "mode": sq["mode"],
                                "sql_hit": bool(sq.get("sql_results")),
                                "vector_hits": len(sq.get("vector_docs", [])),
                            }
                            for sq in sqs
                        ]
                    })

                elif kind == "on_chain_end" and name == "evaluate":
                    data = event["data"]["output"]
                    sqs = data.get("sub_questions", [])
                    yield _sse("evaluate", {
                        "sub_questions": [
                            {
                                "question": sq["question"],
                                "status": sq["status"],
                                "score": round(sq.get("relevance_score", 0), 3),
                            }
                            for sq in sqs
                        ]
                    })

                elif kind == "on_chain_end" and name == "rewrite":
                    data = event["data"]["output"]
                    sqs = data.get("sub_questions", [])
                    yield _sse("rewrite", {
                        "sub_questions": [
                            {
                                "question": sq["question"],
                                "new_search_query": sq.get("search_query"),
                            }
                            for sq in sqs if sq.get("status") == "pending"
                        ]
                    })

                elif kind == "on_chain_end" and name == "generate":
                    data = event["data"]["output"]
                    yield _sse("answer", {
                        "answer": data.get("final_answer"),
                        "sources": data.get("sources", []),
                    })

        except Exception as e:
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── file management ───────────────────────────────────────────────────────────

@app.get("/files")
def list_files():
    """Return uploaded PDFs grouped by company."""
    companies: dict[str, list] = {}
    for pdf in sorted(RAW_DIR.glob("*.pdf")):
        parts = pdf.stem.split("_")
        company = parts[0].capitalize()
        year = parts[1] if len(parts) > 1 else "unknown"
        companies.setdefault(company, []).append({
            "filename": pdf.name,
            "year": year,
            "size_kb": round(pdf.stat().st_size / 1024),
        })
    return {"companies": companies}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a PDF and run ingestion."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    dest = RAW_DIR / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Run ingestion in background thread
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _ingest_file, dest)

    return {"status": "ok", "filename": file.filename}


@app.get("/pdf/{filename}")
def serve_pdf(filename: str):
    path = RAW_DIR / filename
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="application/pdf")


# ── helpers ───────────────────────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _ingest_file(pdf_path: Path):
    init_db(DB_PATH)
    parts     = pdf_path.stem.split("_")
    company   = parts[0].lower()
    year      = int(parts[-1]) if parts[-1].isdigit() else 0
    report_id = f"{company}_{year}"
    ticker    = COMPANY_TICKER_MAP.get(company)

    register_company(company, ticker, DB_PATH)
    register_report(report_id, company, year, pdf_path.name, DB_PATH)

    if not is_already_ingested(report_id, DB_PATH):
        parsed = parse_pdf(str(pdf_path))
        parents, children = chunk_documents_hierarchical(
            parsed["text_chunks"], report_id=report_id
        )
        embed_and_store(parents, children, collection_name=COLLECTION, db_path=DB_PATH)

    fetch_and_store(company, db_path=DB_PATH)

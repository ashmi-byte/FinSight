"""
Ingestion pipeline — two tracks:

  Text track:  PDF → Docling → parent/child chunks → SQLite + Qdrant
  Data track:  company name → yfinance → financial metrics → SQLite

Usage:
    python ingestion/run_ingestion.py
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.db_schema import init_db, register_company, register_report, is_already_ingested
from ingestion.pdf_parser import parse_pdf
from ingestion.text_chunker import chunk_documents_hierarchical
from ingestion.embedder import embed_and_store
from ingestion.financial_data_fetcher import fetch_and_store, COMPANY_TICKER_MAP

RAW_DIR   = Path("data/raw")
DB_PATH   = "data/financials.db"
COLLECTION = "financial_reports"


def main():
    init_db(DB_PATH)

    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {RAW_DIR}")
        return

    seen_companies: set[str] = set()

    for pdf in pdfs:
        parts   = pdf.stem.split("_")
        company = parts[0].lower()
        year    = int(parts[-1]) if parts[-1].isdigit() else 0
        report_id = f"{company}_{year}"
        ticker  = COMPANY_TICKER_MAP.get(company)

        register_company(company, ticker, DB_PATH)
        register_report(report_id, company, year, pdf.name, DB_PATH)

        print(f"\n[Text track] {pdf.name}  (report_id={report_id})")
        if is_already_ingested(report_id, DB_PATH):
            print("  Already ingested, skipping.")
            seen_companies.add(company)
            continue

        parsed = parse_pdf(str(pdf))
        parents, children = chunk_documents_hierarchical(
            parsed["text_chunks"], report_id=report_id
        )
        print(f"  {len(parents)} parent chunks, {len(children)} child chunks")
        embed_and_store(parents, children, collection_name=COLLECTION, db_path=DB_PATH)
        seen_companies.add(company)

    print("\n[Data track] yfinance → SQLite")
    for company in sorted(seen_companies):
        fetch_and_store(company, db_path=DB_PATH)

    print("\nDone.")


if __name__ == "__main__":
    main()

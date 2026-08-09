import sqlite3
import os
import json
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

DB_PATH = os.getenv("SQLITE_PATH", "data/financials.db")

VALID_SECTIONS = {"income_statement", "balance_sheet", "cash_flow"}

SCHEMA = """
Table: financials
Columns:
  company     TEXT    -- e.g. 'google', 'apple', 'microsoft'
  ticker      TEXT    -- e.g. 'GOOGL', 'AAPL', 'MSFT'
  data_year   INTEGER -- fiscal year, e.g. 2024
  metric      TEXT    -- financial metric name
  value       REAL    -- raw USD value (e.g. 350000000000 = $350B)
  section     TEXT    -- 'income_statement', 'balance_sheet', 'cash_flow'
  period      TEXT    -- always 'annual'
  currency    TEXT    -- always 'USD'
"""

STAGE1_PROMPT = """Analyze this financial question and return JSON with three fields:
- "sections": list of relevant sections from ["income_statement", "balance_sheet", "cash_flow"]
- "companies": list of company names in lowercase (e.g. ["google", "apple"]), empty list if unspecified
- "years": list of integer fiscal years mentioned (e.g. [2023, 2024]), empty list if unspecified or asking for latest

Question: {question}

Return only valid JSON, no explanation."""

STAGE2_SYSTEM = """You are a SQL expert for a financial database.

{schema}

Available metrics by section (use exact spelling, all lowercase):
{metric_list}

Rules:
- Filter by company using lowercase (e.g. WHERE company = 'google')
- metric names must exactly match the available metrics listed above
- values are raw USD; to display in billions divide by 1e9
- When specific years are mentioned, filter with data_year (e.g. WHERE data_year = 2023)
- When no year is specified, use the most recent year: ORDER BY data_year DESC with appropriate LIMIT
- Return only valid SQLite SQL, no explanation, no markdown
"""

MAX_SQL_RETRIES = 3


def _get_metrics_for_sections(sections: list, db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    result = {}
    try:
        for section in sections:
            cursor = conn.execute(
                "SELECT DISTINCT metric FROM financials WHERE section = ? ORDER BY metric",
                (section,),
            )
            result[section] = [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()
    return result


def _stage1_parse(question: str) -> dict:
    raw = llm.invoke(STAGE1_PROMPT.format(question=question)).content.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}

    sections = [s for s in parsed.get("sections", []) if s in VALID_SECTIONS]
    if not sections:
        sections = list(VALID_SECTIONS)  # fallback: search all sections

    companies = [c.lower() for c in parsed.get("companies", []) if isinstance(c, str)]
    years = [y for y in parsed.get("years", []) if isinstance(y, int)]

    return {"sections": sections, "companies": companies, "years": years}


def _get_available_filters(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        companies = [r[0] for r in conn.execute(
            "SELECT DISTINCT company FROM financials ORDER BY company"
        ).fetchall()]
        years = [r[0] for r in conn.execute(
            "SELECT DISTINCT data_year FROM financials ORDER BY data_year"
        ).fetchall()]
        return {"companies": companies, "years": years}
    finally:
        conn.close()


def sql_search(question: str, db_path: str = DB_PATH) -> dict:
    # Stage 1: extract sections / companies / years from the question
    meta = _stage1_parse(question)

    # Fetch actual metric names from DB for the relevant sections
    metrics_by_section = _get_metrics_for_sections(meta["sections"], db_path)
    metric_list = "\n".join(
        f"{section}:\n  " + ", ".join(metrics)
        for section, metrics in metrics_by_section.items()
        if metrics
    )

    # Build context hint to append to user message
    hints = []
    if meta["companies"]:
        hints.append("Companies: " + ", ".join(meta["companies"]))
    if meta["years"]:
        hints.append("Years: " + ", ".join(str(y) for y in meta["years"]))

    user_content = question
    if hints:
        user_content += "\n\n[Extracted context: " + "; ".join(hints) + "]"

    # Stage 2: generate SQL with real metric list
    messages = [
        {"role": "system", "content": STAGE2_SYSTEM.format(schema=SCHEMA, metric_list=metric_list)},
        {"role": "user", "content": user_content},
    ]

    available = None  # lazy-load only if we hit a 0-row result

    for attempt in range(MAX_SQL_RETRIES):
        sql = llm.invoke(messages).content.strip().strip("```sql").strip("```").strip()
        result = _execute(sql, db_path)

        if result["error"] is None and result["results"]:
            return result

        messages.append({"role": "assistant", "content": sql})

        if result["error"]:
            messages.append({
                "role": "user",
                "content": f"That SQL returned an error: {result['error']}\nFix the SQL and return only the corrected query.",
            })
        else:
            # Valid SQL but 0 rows — give the LLM concrete hints to self-correct
            if available is None:
                available = _get_available_filters(db_path)
            messages.append({
                "role": "user",
                "content": (
                    f"The SQL executed successfully but returned 0 rows.\n"
                    f"Available companies in DB: {', '.join(available['companies'])}.\n"
                    f"Available years in DB: {', '.join(str(y) for y in available['years'])}.\n"
                    f"Check company name spelling, metric name, and year filter, then return corrected SQL."
                ),
            })

    return {"sql": sql, "results": [], "error": result.get("error"), "failed": True}


def _execute(sql: str, db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        return {
            "sql": sql,
            "results": [dict(zip(columns, row)) for row in rows],
            "error": None,
            "failed": False,
        }
    except Exception as e:
        return {"sql": sql, "results": [], "error": str(e), "failed": False}
    finally:
        conn.close()

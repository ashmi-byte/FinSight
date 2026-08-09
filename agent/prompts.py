CLASSIFY_PROMPT = """Classify this financial question and decide the retrieval mode.

Question: {question}

Return JSON with these fields:
{{
  "type": "simple" | "multihop" | "cross_document",
  "mode": "sql" | "vector",
  "company": "<lowercase company name>" | null,
  "year": <integer fiscal year> | null
}}

type rules:
- simple: single fact, one company, one metric, one time period — AND needs only one retrieval type
- multihop: requires chaining multiple facts, OR needs both a number AND an explanation/reason
- cross_document: comparing across companies OR multi-year analysis

mode rules (only applies when type is simple):
- sql:    asks for a specific number (revenue, profit, R&D, CapEx, assets, EPS, etc.)
- vector: asks for reasoning, strategy, risk, management commentary, qualitative context

company: lowercase name of the company if clearly stated (e.g. "google", "apple"), otherwise null
year: fiscal year integer if clearly stated (e.g. 2023), otherwise null

If the question needs both a number AND an explanation, set type to multihop so it gets decomposed.

Return only valid JSON, no explanation."""


DECOMPOSE_PROMPT = """Break this financial question into 2-4 sub-questions.
For each sub-question provide:
- "question": the sub-question in plain language
- "search_query": a retrieval-optimized version using financial report terminology
- "mode": "sql" | "vector"
- "company": the specific company this sub-question is about (e.g. "google", "apple", "meta"), or null if it spans multiple companies
- "year": the fiscal year as an integer (e.g. 2023), or null if not specified

Original question: {question}

mode rules:
- sql:    specific metrics (revenue, net income, R&D expenses, capital expenditure, EPS, total assets)
- vector: reasoning, strategy, risk factors, management discussion, qualitative analysis

Example output:
[
  {{
    "question": "What was Google's R&D spending in 2023?",
    "search_query": "research and development expenses 2023 annual",
    "mode": "sql",
    "company": "google",
    "year": 2023
  }},
  {{
    "question": "What was Meta's R&D spending in 2023?",
    "search_query": "research and development expenses 2023 annual",
    "mode": "sql",
    "company": "meta",
    "year": 2023
  }},
  {{
    "question": "Why did Google increase R&D investment?",
    "search_query": "research development investment strategy AI focus management discussion",
    "mode": "vector",
    "company": "google",
    "year": null
  }}
]

Return only valid JSON array, no explanation."""


REWRITE_PROMPT = """A retrieval attempt for the following sub-question returned insufficient results.
Rewrite the search query to improve retrieval from financial reports.

Sub-question: {question}
Original search query: {search_query}
Retrieved snippets (low quality): {failed_snippets}

Rewrite the search query to be more specific, using different financial terminology.
Return only the rewritten search query, no explanation."""


GENERATE_PROMPT = """You are a financial analyst assistant. Answer the question using ONLY the provided context.

Rules:
- Quote exact numbers when available; always state the company and year
- For numbers from Financial Data, cite as (Financial Data)
- For numbers from Document Excerpts, cite as (Source: company year p.page)
- If a sub-question is marked BEST EFFORT, state clearly that information was insufficient
- Be concise and precise

{context}

Question: {question}

Answer:"""

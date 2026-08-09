"""
Pull structured financial data from Yahoo Finance via yfinance.
Covers Income Statement, Balance Sheet, and Cash Flow for annual periods.
"""
import sqlite3
import pandas as pd
import yfinance as yf

COMPANY_TICKER_MAP = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "meta": "META",
    "nvidia": "NVDA",
}

STATEMENTS = [
    ("income_statement", "financials"),
    ("balance_sheet",    "balance_sheet"),
    ("cash_flow",        "cashflow"),
]


def fetch_financials(company: str) -> pd.DataFrame:
    ticker_symbol = COMPANY_TICKER_MAP.get(company.lower())
    if not ticker_symbol:
        print(f"  [WARN] No ticker mapping for '{company}', skipping.")
        return pd.DataFrame()

    ticker = yf.Ticker(ticker_symbol)
    rows = []

    for section, attr in STATEMENTS:
        try:
            df = getattr(ticker, attr)
        except Exception as e:
            print(f"  [WARN] Could not fetch {section} for {ticker_symbol}: {e}")
            continue

        if df is None or df.empty:
            continue

        for date_col in df.columns:
            data_year = pd.to_datetime(date_col).year
            for metric, value in df[date_col].items():
                if pd.isna(value):
                    continue
                rows.append({
                    "company":   company.lower(),
                    "ticker":    ticker_symbol,
                    "data_year": data_year,
                    "metric":    str(metric).lower().strip(),
                    "value":     float(value),
                    "section":   section,
                    "period":    "annual",
                    "currency":  "USD",
                })

    return pd.DataFrame(rows)


def store_to_sqlite(df: pd.DataFrame, db_path: str):
    if df.empty:
        return
    conn = sqlite3.connect(db_path)
    for company in df["company"].unique():
        conn.execute("DELETE FROM financials WHERE company = ?", (company,))
    df.to_sql("financials", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()


def fetch_and_store(company: str, db_path: str):
    print(f"  Fetching {company} financials from Yahoo Finance ...")
    df = fetch_financials(company)
    if df.empty:
        print(f"  [SKIP] No data returned for {company}.")
        return
    print(f"  {len(df)} rows → SQLite")
    store_to_sqlite(df, db_path)

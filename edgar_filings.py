"""
SEC EDGAR Filing Fetcher
------------------------
Fetches the latest 10-K and 10-Q filings for any public company
using its stock ticker symbol. No API key required.

Usage:
    python3 edgar_filings.py
    python3 edgar_filings.py AAPL
    python3 edgar_filings.py MSFT
"""

import sys
import json
import gzip
import urllib.request
import urllib.error


# SEC EDGAR requires a User-Agent header identifying who you are.
# Replace with your name/email if you plan to use this regularly.
HEADERS = {
    "User-Agent": "edgar-fetcher contact@example.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}


def fetch_json(url: str, headers: dict) -> dict:
    """Make a GET request and return the parsed JSON response."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read()
            # EDGAR often returns gzip-compressed data
            try:
                raw = gzip.decompress(raw)
            except (gzip.BadGzipFile, OSError):
                pass  # not gzipped, use as-is
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  HTTP error {e.code}: {e.reason}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"  Network error: {e.reason}")
        sys.exit(1)


def get_cik(ticker: str) -> tuple[str, str]:
    """
    Look up a company's CIK number from its ticker symbol.
    CIK is the unique ID SEC uses to identify every public company.

    Returns:
        (cik_padded, company_name) — CIK zero-padded to 10 digits
    """
    print(f"  Looking up CIK for ticker '{ticker.upper()}'...")

    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {**HEADERS, "Host": "www.sec.gov"}
    data = fetch_json(url, headers)

    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry["ticker"].upper() == ticker_upper:
            cik_raw = str(entry["cik_str"])
            cik_padded = cik_raw.zfill(10)   # SEC wants a 10-digit CIK
            company_name = entry["title"]
            return cik_padded, company_name

    print(f"\n  Could not find ticker '{ticker}'. Check the symbol and try again.")
    sys.exit(1)


def get_filings(cik: str) -> dict:
    """
    Fetch the full submission history for a company from EDGAR.
    This includes every filing the company has ever made.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    return fetch_json(url, HEADERS)


def extract_filings(filings_data: dict, form_type: str, limit: int = 5) -> list[dict]:
    """
    Filter filings by form type (e.g. '10-K' or '10-Q') and return
    the most recent ones.

    Each filing is returned as a dict with:
        accessionNumber, filingDate, reportDate, primaryDocument
    """
    recent = filings_data.get("filings", {}).get("recent", {})

    # The API returns parallel lists — zip them into rows
    forms        = recent.get("form", [])
    dates        = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    accessions   = recent.get("accessionNumber", [])
    documents    = recent.get("primaryDocument", [])

    results = []
    for form, date, report, accession, doc in zip(forms, dates, report_dates, accessions, documents):
        if form == form_type:
            results.append({
                "filingDate":  date,
                "reportDate":  report,
                "accession":   accession,
                "document":    doc,
            })
        if len(results) == limit:
            break

    return results


def build_filing_url(cik: str, accession: str, document: str) -> str:
    """Build the direct EDGAR viewer URL for a filing."""
    acc_clean = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{document}"


def print_filings(label: str, filings: list[dict], cik: str) -> None:
    """Pretty-print a list of filings."""
    print(f"\n  {'─' * 55}")
    print(f"  {label} Filings")
    print(f"  {'─' * 55}")

    if not filings:
        print("  No filings found.")
        return

    for i, f in enumerate(filings, start=1):
        url = build_filing_url(cik, f["accession"], f["document"])
        print(f"\n  [{i}]  Filing date : {f['filingDate']}")
        print(f"       Report date : {f['reportDate'] or 'N/A'}")
        print(f"       Accession # : {f['accession']}")
        print(f"       URL         : {url}")


def main():
    # ── Get the ticker from the command line or prompt the user ──────────────
    if len(sys.argv) > 1:
        ticker = sys.argv[1].strip()
    else:
        ticker = input("Enter a stock ticker symbol (e.g. AAPL, MSFT, TSLA): ").strip()

    if not ticker:
        print("No ticker provided. Exiting.")
        sys.exit(1)

    print(f"\n{'═' * 60}")
    print(f"  SEC EDGAR Filing Lookup")
    print(f"{'═' * 60}")

    # ── Step 1: Resolve ticker → CIK ─────────────────────────────────────────
    cik, company_name = get_cik(ticker)
    print(f"  Company : {company_name}")
    print(f"  CIK     : {cik.lstrip('0')}  (padded: {cik})")

    # ── Step 2: Fetch all submission history ──────────────────────────────────
    print(f"\n  Fetching filings from EDGAR...")
    filings_data = get_filings(cik)

    # ── Step 3: Extract and display 10-K and 10-Q filings ────────────────────
    annual   = extract_filings(filings_data, "10-K", limit=3)
    quarterly = extract_filings(filings_data, "10-Q", limit=5)

    print_filings("10-K  (Annual Report)", annual, cik)
    print_filings("10-Q  (Quarterly Report)", quarterly, cik)

    print(f"\n{'═' * 60}")
    print(f"  Done! Open any URL above to read the full filing on SEC.gov")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()

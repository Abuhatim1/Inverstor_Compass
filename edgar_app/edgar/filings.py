"""
edgar/filings.py
----------------
Business logic for looking up companies and extracting filings.
No UI or network code here — all network calls go through client.py.
"""

from dataclasses import dataclass

from .client import EdgarAPIError, fetch_company_tickers, fetch_submissions


@dataclass
class Filing:
    form_type: str
    filing_date: str
    report_date: str
    accession: str
    document: str
    url: str


@dataclass
class CompanyInfo:
    ticker: str
    name: str
    cik: str          # raw (no leading zeros)
    cik_padded: str   # 10-digit zero-padded


def lookup_company(ticker: str) -> CompanyInfo:
    """
    Resolve a ticker symbol to a CompanyInfo.
    Raises EdgarAPIError if the ticker is not found.
    """
    data = fetch_company_tickers()
    ticker_upper = ticker.strip().upper()

    for entry in data.values():
        if entry["ticker"].upper() == ticker_upper:
            cik_raw = str(entry["cik_str"])
            return CompanyInfo(
                ticker=ticker_upper,
                name=entry["title"],
                cik=cik_raw,
                cik_padded=cik_raw.zfill(10),
            )

    raise EdgarAPIError(
        f"Ticker '{ticker.upper()}' not found. "
        "Make sure it is a valid US exchange ticker (NYSE/NASDAQ)."
    )


def _build_url(cik: str, accession: str, document: str) -> str:
    """Build a direct SEC.gov filing URL."""
    acc_clean = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{document}"


def get_filings(company: CompanyInfo, form_type: str, limit: int = 5) -> list[Filing]:
    """
    Return the most recent filings of a given type for a company.

    form_type examples: '10-K', '10-Q', '8-K'
    """
    submissions = fetch_submissions(company.cik_padded)
    recent = submissions.get("filings", {}).get("recent", {})

    forms        = recent.get("form", [])
    dates        = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    accessions   = recent.get("accessionNumber", [])
    documents    = recent.get("primaryDocument", [])

    results: list[Filing] = []
    for form, date, report, accession, doc in zip(
        forms, dates, report_dates, accessions, documents
    ):
        if form == form_type:
            results.append(
                Filing(
                    form_type=form,
                    filing_date=date,
                    report_date=report or "N/A",
                    accession=accession,
                    document=doc,
                    url=_build_url(company.cik, accession, doc),
                )
            )
        if len(results) == limit:
            break

    return results

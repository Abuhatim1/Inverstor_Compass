"""
edgar/client.py
---------------
Low-level HTTP client for the SEC EDGAR API.
All network calls live here so the rest of the app never touches urllib directly.
"""

import gzip
import json
import urllib.error
import urllib.request
from typing import Any

# SEC EDGAR requires a descriptive User-Agent.
# Update this with your name/email if you use this app heavily.
HEADERS_DATA = {
    "User-Agent": "edgar-app contact@example.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

HEADERS_WWW = {
    "User-Agent": "edgar-app contact@example.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}


class EdgarAPIError(Exception):
    """Raised when the EDGAR API returns an error or is unreachable."""


def _fetch_json(url: str, headers: dict[str, str]) -> Any:
    """Make a GET request and return the parsed JSON. Handles gzip transparently."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read()
            try:
                raw = gzip.decompress(raw)
            except (gzip.BadGzipFile, OSError):
                pass
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise EdgarAPIError(f"HTTP {exc.code}: {exc.reason} — {url}") from exc
    except urllib.error.URLError as exc:
        raise EdgarAPIError(f"Network error: {exc.reason}") from exc


def fetch_company_tickers() -> dict:
    """Return the full SEC company-ticker lookup table."""
    url = "https://www.sec.gov/files/company_tickers.json"
    return _fetch_json(url, HEADERS_WWW)


def fetch_submissions(cik_padded: str) -> dict:
    """
    Return raw submission history for a company.
    cik_padded must be a 10-digit zero-padded CIK string, e.g. '0000320193'.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    return _fetch_json(url, HEADERS_DATA)

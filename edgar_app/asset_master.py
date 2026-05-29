"""
asset_master.py
---------------
Central Asset Resolver for the بوصلة app.

resolve_asset(ticker) → AssetRecord

Given a ticker string, queries Yahoo Finance (max 5-second timeout)
and returns a structured AssetRecord with all fields needed to pre-fill
Add Holding / Edit Holding / Transaction / Watchlist forms.

If Yahoo Finance fails or times out, returns a Manual-priced record
with only the ticker filled in — never blocks asset creation.

Results are cached in Streamlit session_state (30-minute TTL) so that
repeated lookups during a session don't hit the network.

Usage:
    from asset_master import resolve_asset, AssetRecord
    rec = resolve_asset("AAPL")
    if rec.yahoo_available:
        # use rec.company_name, rec.currency, rec.current_price …
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from datetime import datetime


# ── Cache settings ────────────────────────────────────────────────────────────
_SESSION_KEY = "asset_master_cache"
_CACHE_TTL   = 1800   # 30 minutes
_YF_TIMEOUT  = 5.0    # seconds


# ── Exchange → Market mapping ─────────────────────────────────────────────────
_EXCHANGE_TO_MARKET: dict[str, str] = {
    "NMS": "US", "NYQ": "US", "NGM": "US", "PCX": "US", "ASE": "US",
    "BTS": "US",
    "SAU": "Saudi", "SAR": "Saudi",
    "LSE": "UK",    "IOB": "UK",
    "FRA": "Europe","ETR": "Europe","EPA": "Europe","AMS": "Europe",
    "TSE": "Asia",  "OSA": "Asia", "SHH": "Asia", "SHZ": "Asia",
    "HKG": "Asia",  "KSE": "Asia",
}

# ── Asset type guesses from Yahoo quoteType ────────────────────────────────────
_QUOTE_TYPE_MAP: dict[str, str] = {
    "EQUITY":    "Stock",
    "ETF":       "ETF",
    "MUTUALFUND":"Fund",
    "COMMODITY": "Commodity",
    "CURRENCY":  "Cash",
    "FUTURE":    "Other",
    "INDEX":     "Other",
}


@dataclass
class AssetRecord:
    ticker:          str
    yahoo_available: bool  = False
    company_name:    str   = ""
    asset_type:      str   = "Stock"
    exchange:        str   = ""
    market:          str   = "US"
    currency:        str   = "USD"
    current_price:   float = 0.0
    price_source:    str   = "manual"
    last_updated:    str   = ""
    sec_available:   bool  = False
    cik:             str   = ""
    pricing_mode:    str   = "Manual-priced"   # "Yahoo-linked" | "Manual-priced"
    error_msg:       str   = ""


def _fetch_from_yf(ticker: str) -> AssetRecord:
    """Blocking yfinance call — run inside a thread with a timeout."""
    import yfinance as yf
    tk = yf.Ticker(ticker)

    # Try fast_info first (much faster than .info)
    fi  = tk.fast_info
    inf = {}
    try:
        inf = tk.info or {}
    except Exception:
        pass

    # Price
    price = (
        getattr(fi, "last_price", None)
        or getattr(fi, "regular_market_price", None)
        or inf.get("regularMarketPrice")
        or inf.get("currentPrice")
        or 0.0
    )
    try:
        price = float(price) if price else 0.0
    except (TypeError, ValueError):
        price = 0.0

    # Currency
    currency = (
        getattr(fi, "currency", None)
        or inf.get("currency", "USD")
        or "USD"
    )

    # Company name
    company_name = (
        inf.get("longName")
        or inf.get("shortName")
        or getattr(fi, "name", None)
        or ticker
    )

    # Exchange / market
    exchange = inf.get("exchange", "") or getattr(fi, "exchange", "") or ""
    market   = _EXCHANGE_TO_MARKET.get(exchange, "US") if exchange else "US"

    # Asset type
    quote_type = inf.get("quoteType", "EQUITY").upper()
    asset_type = _QUOTE_TYPE_MAP.get(quote_type, "Stock")

    ok = price > 0 or bool(company_name and company_name != ticker)

    return AssetRecord(
        ticker          = ticker,
        yahoo_available = ok,
        company_name    = company_name,
        asset_type      = asset_type,
        exchange        = exchange,
        market          = market,
        currency        = currency,
        current_price   = price,
        price_source    = "yfinance" if ok else "manual",
        last_updated    = datetime.now().isoformat(),
        pricing_mode    = "Yahoo-linked" if ok else "Manual-priced",
    )


def resolve_asset(ticker: str, timeout: float = _YF_TIMEOUT) -> AssetRecord:
    """
    Resolve a ticker to an AssetRecord.
    - Tries yfinance with a `timeout`-second timeout.
    - Falls back to a Manual-priced stub on any failure.
    - Never raises.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return AssetRecord(ticker="", error_msg="Ticker is empty.")

    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_fetch_from_yf, ticker)
        try:
            return fut.result(timeout=timeout)
        except FuturesTimeout:
            return AssetRecord(
                ticker       = ticker,
                error_msg    = f"Yahoo Finance timed out after {timeout:.0f}s.",
                pricing_mode = "Manual-priced",
            )
        except Exception as exc:
            return AssetRecord(
                ticker       = ticker,
                error_msg    = str(exc),
                pricing_mode = "Manual-priced",
            )


# ── Session-state cache ───────────────────────────────────────────────────────

def resolve_asset_cached(ticker: str) -> AssetRecord:
    """
    Same as resolve_asset() but caches results in Streamlit session_state
    for up to 30 minutes. Call this from UI code.
    """
    import streamlit as st

    ticker = (ticker or "").strip().upper()
    if not ticker:
        return AssetRecord(ticker="")

    cache     = st.session_state.get(_SESSION_KEY, {})
    cache_ts  = st.session_state.get(f"{_SESSION_KEY}_ts", {})
    now       = time.monotonic()

    if ticker in cache and (now - cache_ts.get(ticker, 0)) < _CACHE_TTL:
        return cache[ticker]

    rec = resolve_asset(ticker)
    cache[ticker]    = rec
    cache_ts[ticker] = now
    st.session_state[_SESSION_KEY]         = cache
    st.session_state[f"{_SESSION_KEY}_ts"] = cache_ts
    return rec


def bust_cache(ticker: str) -> None:
    """Force the next resolve_asset_cached() call to re-fetch from Yahoo."""
    import streamlit as st
    cache_ts = st.session_state.get(f"{_SESSION_KEY}_ts", {})
    cache_ts.pop(ticker, None)
    st.session_state[f"{_SESSION_KEY}_ts"] = cache_ts

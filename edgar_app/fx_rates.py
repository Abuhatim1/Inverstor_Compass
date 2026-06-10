"""
fx_rates.py
-----------
FX rate fetching and conversion for multi-currency portfolio valuation.

Converts any holding's local currency to the user's chosen base currency
(default: SAR) so that portfolio totals are always apples-to-apples.

Priority (per pair):
  1. yfinance direct pair   e.g. USDSAR=X  → USD→SAR
  2. yfinance reverse pair  e.g. SARUSD=X  → invert
  3. USD-pivot              from→USD via yfinance, USD→base via yfinance
  4. Built-in default rates (clearly labelled as "default")

Session-state cache with 5-minute TTL avoids repeated API calls on every
Streamlit rerun.

Usage:
    from fx_rates import get_rates_for_holdings, FxRate
    fx = get_rates_for_holdings(["USD", "SAR", "EUR"], base_ccy="SAR")
    rate_usd_to_sar = fx["USD"].rate   # ≈ 3.75
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import NamedTuple

_SESSION_KEY = "fx_rate_cache"
_CACHE_TTL   = 300   # 5 minutes (only used when live FX is enabled)


# ── Static-only helper (used when live FX toggle is OFF) ──────────────────────

def _get_default_rates(currencies: list[str], base_ccy: str) -> "dict[str, FxRate]":
    """Return rates computed purely from _DEFAULT_TO_USD — zero network calls."""
    now = datetime.now().isoformat()
    result: dict[str, FxRate] = {}
    base_usd = _DEFAULT_TO_USD.get(base_ccy, 1.0)
    for ccy in set(currencies):
        if ccy == base_ccy:
            result[ccy] = FxRate(ccy, base_ccy, 1.0, "same", now)
        else:
            from_usd = _DEFAULT_TO_USD.get(ccy, 1.0)
            rate = from_usd / base_usd if base_usd else 1.0
            result[ccy] = FxRate(ccy, base_ccy, rate, "default", now)
    return result


# ── Default rates (all relative to USD) ───────────────────────────────────────
# Used when yfinance cannot return a live quote.
# USD-pegged: SAR (3.75), AED (3.6725), QAR (3.64)
_DEFAULT_TO_USD: dict[str, float] = {
    "USD":   1.000000,
    "SAR":   0.266667,   # 1 SAR = 0.2667 USD  (1 USD = 3.75 SAR)
    "AED":   0.272294,   # pegged
    "KWD":   3.250000,   # approx
    "QAR":   0.274725,   # pegged
    "EUR":   1.100000,   # approx
    "GBP":   1.270000,   # approx
    "CNY":   0.138000,   # approx
    "JPY":   0.006700,   # approx
    "Other": 1.000000,   # treated as USD equivalent
}


# ── Result type ───────────────────────────────────────────────────────────────

class FxRate(NamedTuple):
    from_ccy:   str    # e.g. "USD"
    base_ccy:   str    # e.g. "SAR"
    rate:       float  # 1 unit of from_ccy → this many units of base_ccy
    source:     str    # "same" | "live" | "default"
    fetched_at: str    # ISO timestamp


# ── Low-level yfinance probe ───────────────────────────────────────────────────

def _yf_price(pair: str) -> float | None:
    """Return the last price of a yfinance symbol, or None on any failure."""
    try:
        import yfinance as yf
        tk = yf.Ticker(pair)
        # Probe 1: fast_info
        fi = tk.fast_info
        p = getattr(fi, "last_price", None) or getattr(fi, "regular_market_price", None)
        if p and float(p) > 0:
            return float(p)
        # Probe 2: info dict
        info = tk.info or {}
        for key in ("regularMarketPrice", "currentPrice", "previousClose"):
            v = info.get(key)
            if v and float(v) > 0:
                return float(v)
        # Probe 3: recent history
        hist = tk.history(period="2d")
        if hist is not None and not hist.empty:
            c = hist["Close"].dropna()
            if len(c) > 0:
                return float(c.iloc[-1])
    except Exception:
        pass
    return None


# ── Core rate resolution ───────────────────────────────────────────────────────

def get_rate(from_ccy: str, base_ccy: str) -> FxRate:
    """
    Return FxRate: how many units of base_ccy equals 1 unit of from_ccy.
    Tries yfinance first, falls back to built-in defaults. Never raises.
    """
    from_ccy = (from_ccy or "USD").upper()
    base_ccy = (base_ccy or "SAR").upper()
    now = datetime.now().isoformat()

    if from_ccy == base_ccy:
        return FxRate(from_ccy, base_ccy, 1.0, "same", now)

    # 1. Direct yfinance pair: USDSAR=X
    p = _yf_price(f"{from_ccy}{base_ccy}=X")
    if p:
        return FxRate(from_ccy, base_ccy, p, "live", now)

    # 2. Reverse pair: SARUSD=X  → invert
    q = _yf_price(f"{base_ccy}{from_ccy}=X")
    if q and q != 0:
        return FxRate(from_ccy, base_ccy, 1.0 / q, "live", now)

    # 3. Pivot through USD when neither ccy is USD
    if from_ccy != "USD" and base_ccy != "USD":
        from_usd = _yf_price(f"{from_ccy}USD=X")
        if from_usd is None:
            rev = _yf_price(f"USD{from_ccy}=X")
            from_usd = (1.0 / rev) if (rev and rev != 0) else _DEFAULT_TO_USD.get(from_ccy, 1.0)

        usd_base = _yf_price(f"USD{base_ccy}=X")
        if usd_base is None:
            rev2 = _yf_price(f"{base_ccy}USD=X")
            usd_base = (1.0 / rev2) if (rev2 and rev2 != 0) else None

        if usd_base:
            return FxRate(from_ccy, base_ccy, from_usd * usd_base, "live", now)

    # 4. Default rates (USD-pivot, static)
    from_usd_d = _DEFAULT_TO_USD.get(from_ccy, 1.0)
    base_usd_d = _DEFAULT_TO_USD.get(base_ccy, 1.0)
    rate = from_usd_d / base_usd_d if base_usd_d else 1.0
    return FxRate(from_ccy, base_ccy, rate, "default", now)


# ── Batch with session-state cache ────────────────────────────────────────────

def get_rates_for_holdings(
    currencies: list[str],
    base_ccy: str,
) -> dict[str, FxRate]:
    """
    Batch-fetch FX rates for all currencies in the portfolio.

    When st.session_state["live_fx_enabled"] is False (the default), returns
    static built-in rates instantly — no network call.  When True, hits
    Yahoo Finance and caches results in session state for 5 minutes.
    Returns {currency: FxRate}.
    """
    try:
        import streamlit as st
        if not st.session_state.get("live_fx_enabled", False):
            return _get_default_rates(currencies, base_ccy)
    except Exception:
        pass

    import streamlit as st

    cache_key  = f"{_SESSION_KEY}_{base_ccy}"
    age_key    = f"{cache_key}_ts"
    now_ts     = time.monotonic()
    cached     = st.session_state.get(cache_key, {})
    cached_ts  = st.session_state.get(age_key, 0.0)
    ttl_ok     = (now_ts - cached_ts) < _CACHE_TTL
    needed     = [c for c in set(currencies) if c not in cached or not ttl_ok]

    if needed:
        result = dict(cached) if ttl_ok else {}
        for ccy in needed:
            result[ccy] = get_rate(ccy, base_ccy)
        st.session_state[cache_key] = result
        st.session_state[age_key]   = now_ts
        return result

    return cached


def refresh_fx_rates(currencies: list[str], base_ccy: str) -> dict[str, FxRate]:
    """
    Force-refresh FX rates, bypassing the TTL cache.
    Call this when the user explicitly clicks a Refresh FX button.
    """
    import streamlit as st
    cache_key = f"{_SESSION_KEY}_{base_ccy}"
    age_key   = f"{cache_key}_ts"
    result: dict[str, FxRate] = {}
    for ccy in set(currencies):
        result[ccy] = get_rate(ccy, base_ccy)
    st.session_state[cache_key] = result
    st.session_state[age_key]   = time.monotonic()
    return result

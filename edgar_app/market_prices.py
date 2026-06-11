"""
market_prices.py
----------------
Live market data fetching via yfinance with a transparent price-source chain.

Price priority (per ticker):
  1. fast_info.last_price
  2. info["regularMarketPrice"]
  3. history(period="1d", interval="1m") — last intraday close
  4. previous_close_fallback (clearly labelled)

Design rules:
- Never crashes the app. Every public function returns a safe fallback.
- Does NOT overwrite manually-entered prices unless the caller explicitly applies.
- 60-second in-memory TTL cache.
- Manual refresh always bypasses the cache (force=True).
- Session-state mirrors in-memory cache for UI inspection.
- All raw probe values are stored for the debug table.
"""

from __future__ import annotations

import json
import os
import time
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

CACHE_TTL_SECONDS         = 60          # 1 minute — short so "Refresh" always gets fresh data
_SESSION_CACHE_KEY        = "mp_price_cache"
_SESSION_LAST_REFRESH_KEY = "mp_last_refresh"

# Persistent refresh timestamp — survives app restarts
_REFRESH_TS_FILE = os.path.join(os.path.dirname(__file__), "portfolio", "price_refresh_ts.json")


def save_refresh_ts(epoch: float) -> None:
    """Write last-refresh epoch to disk so the 60-min freshness window survives restarts."""
    try:
        with open(_REFRESH_TS_FILE, "w") as _f:
            json.dump({"ts": epoch}, _f)
    except Exception:
        pass


def load_refresh_ts() -> Optional[float]:
    """Return persisted last-refresh epoch, or None if file is missing or corrupt."""
    try:
        with open(_REFRESH_TS_FILE) as _f:
            d = json.load(_f)
            ts = d.get("ts")
            return float(ts) if ts is not None else None
    except Exception:
        return None

PRICE_SOURCES = {
    "last_price":              "fast_info.last_price",
    "regularMarketPrice":      "info.regularMarketPrice",
    "intraday_1m_close":       "history(1d,1m) close",
    "previous_close_fallback": "⚠️ previousClose (fallback — may not reflect today)",
    "none":                    "—",
}

# ── In-process cache ───────────────────────────────────────────────────────────

_cache: dict[str, tuple["MarketData", float]] = {}
_cache_lock = threading.Lock()


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class MarketData:
    """Live (or best-available) market snapshot for one ticker."""
    ticker:               str

    # Selected price and metadata
    current_price:        Optional[float] = None
    price_source:         str             = "none"   # key from PRICE_SOURCES
    price_timestamp:      str             = ""        # ISO UTC of fetch
    daily_change_pct:     Optional[float] = None

    # Raw probe values (for debug table)
    raw_last_price:       Optional[float] = None   # fast_info.last_price
    raw_regular_market:   Optional[float] = None   # info.regularMarketPrice
    raw_intraday_close:   Optional[float] = None   # history 1m last Close
    raw_previous_close:   Optional[float] = None   # fast_info.previous_close

    # Secondary info
    market_cap:           Optional[float] = None
    volume:               Optional[float] = None
    beta:                 Optional[float] = None
    currency:             str             = "USD"
    error:                Optional[str]  = None

    # ── Derived helpers ───────────────────────────────────────────────────────

    @property
    def is_ok(self) -> bool:
        return self.error is None and self.current_price is not None

    @property
    def is_fallback(self) -> bool:
        return self.price_source == "previous_close_fallback"

    @property
    def day_indicator(self) -> str:
        if self.is_fallback:
            return "⚪"
        if self.daily_change_pct is None:
            return "⚪"
        return "🟢" if self.daily_change_pct > 0 else ("🔴" if self.daily_change_pct < 0 else "⚪")

    @property
    def change_str(self) -> str:
        if self.daily_change_pct is None:
            return "—"
        sign = "+" if self.daily_change_pct >= 0 else ""
        return f"{sign}{self.daily_change_pct:.2f}%"

    @property
    def source_label(self) -> str:
        return PRICE_SOURCES.get(self.price_source, self.price_source)

    @property
    def price_str(self) -> str:
        if self.current_price is None:
            return "Unavailable"
        return f"{self.current_price:.2f} {self.currency}"


def _error_data(ticker: str, reason: str) -> "MarketData":
    return MarketData(
        ticker          = ticker,
        error           = reason,
        price_timestamp = datetime.now(timezone.utc).isoformat(),
    )


# ── Single-ticker fetch ────────────────────────────────────────────────────────

def get_market_data(ticker: str, *, force: bool = False) -> "MarketData":
    """
    Fetch live market data for *ticker* using the full source priority chain.

    Set force=True to bypass the in-memory cache (used by manual refresh).
    Never raises; all errors are captured in .error.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return _error_data(ticker, "Empty ticker")

    now_mono = time.monotonic()
    if not force:
        with _cache_lock:
            cached = _cache.get(ticker)
            if cached and (now_mono - cached[1]) < CACHE_TTL_SECONDS:
                return cached[0]

    try:
        import yfinance as yf
        t = yf.Ticker(ticker)

        # ── Probe 1: fast_info ─────────────────────────────────────────────
        fi = t.fast_info
        raw_lp  = _safe_float(getattr(fi, "last_price",      None))
        raw_pc  = _safe_float(getattr(fi, "previous_close",  None))
        raw_cap = _safe_float(getattr(fi, "market_cap",      None))
        raw_vol = _safe_float(getattr(fi, "three_month_average_volume", None))
        currency = str(getattr(fi, "currency", None) or "USD")

        # ── Probe 2: info (regularMarketPrice + beta) ─────────────────────
        raw_rmp:  Optional[float] = None
        raw_beta: Optional[float] = None
        try:
            info = t.info or {}
            raw_rmp  = _safe_float(info.get("regularMarketPrice"))
            raw_beta = _safe_float(info.get("beta"))
            # info may have a better previousClose
            if raw_pc is None:
                raw_pc = _safe_float(info.get("previousClose"))
            if currency == "USD":
                currency = str(info.get("currency") or "USD")
        except Exception:
            pass

        # ── Probe 3: intraday 1m history ──────────────────────────────────
        raw_intra: Optional[float] = None
        try:
            hist = t.history(period="1d", interval="1m")
            if hist is not None and not hist.empty and "Close" in hist.columns:
                closes = hist["Close"].dropna()
                if len(closes) > 0:
                    raw_intra = float(closes.iloc[-1])
        except Exception:
            pass

        # ── Select price by priority ──────────────────────────────────────
        price:  Optional[float] = None
        source: str             = "none"

        if raw_lp and raw_lp > 0:
            price  = raw_lp
            source = "last_price"
        elif raw_rmp and raw_rmp > 0:
            price  = raw_rmp
            source = "regularMarketPrice"
        elif raw_intra and raw_intra > 0:
            price  = raw_intra
            source = "intraday_1m_close"
        elif raw_pc and raw_pc > 0:
            price  = raw_pc
            source = "previous_close_fallback"

        # ── Daily change ──────────────────────────────────────────────────
        daily_chg: Optional[float] = None
        if price and raw_pc and raw_pc > 0 and source != "previous_close_fallback":
            daily_chg = (price - raw_pc) / raw_pc * 100.0

        if price is None:
            data = _error_data(ticker, "No price returned — ticker may be delisted, unavailable, or rate-limited")
        else:
            data = MarketData(
                ticker            = ticker,
                current_price     = price,
                price_source      = source,
                price_timestamp   = datetime.now(timezone.utc).isoformat(),
                daily_change_pct  = daily_chg,
                raw_last_price    = raw_lp,
                raw_regular_market= raw_rmp,
                raw_intraday_close= raw_intra,
                raw_previous_close= raw_pc,
                market_cap        = raw_cap,
                volume            = raw_vol,
                beta              = raw_beta,
                currency          = currency,
                error             = None,
            )

    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "429" in msg or "rate" in msg.lower():
            msg = "Rate-limited by Yahoo Finance — try again in a few minutes"
        elif "no data" in msg.lower() or "empty" in msg.lower():
            msg = "No data returned — ticker may be invalid or delisted"
        data = _error_data(ticker, msg)

    with _cache_lock:
        _cache[ticker] = (data, time.monotonic())

    return data


def _safe_float(v) -> Optional[float]:
    """Convert a value to float, returning None on failure or non-positive."""
    try:
        f = float(v)
        return f if (f == f) else None    # NaN check
    except (TypeError, ValueError):
        return None


# ── Bulk refresh ──────────────────────────────────────────────────────────────

def refresh_all_prices(
    ticker_list: list[str],
    *,
    force: bool = False,
) -> dict[str, "MarketData"]:
    """
    Fetch live prices for all tickers in *ticker_list*.

    force=True: bypasses the in-memory cache for all tickers (used by the
    manual "Refresh Market Prices" button).

    Strategy: individual per-ticker fetches using the full source-chain so
    every ticker gets the best available price and we can expose the debug
    table. Returns dict[ticker → MarketData].  Never raises.
    """
    tickers = [t.strip().upper() for t in (ticker_list or []) if t.strip()]
    if not tickers:
        return {}

    results: dict[str, MarketData] = {}
    now_mono = time.monotonic()

    if not force:
        with _cache_lock:
            for t in tickers:
                cached = _cache.get(t)
                if cached and (now_mono - cached[1]) < CACHE_TTL_SECONDS:
                    results[t] = cached[0]

    stale = [t for t in tickers if t not in results]
    for t in stale:
        results[t] = get_market_data(t, force=force)

    return results


# ── Market session awareness ──────────────────────────────────────────────────

def is_us_market_open() -> bool:
    try:
        from zoneinfo import ZoneInfo
        et = datetime.now(ZoneInfo("America/New_York"))
        if et.weekday() >= 5:
            return False
        open_t  = et.replace(hour=9,  minute=30, second=0, microsecond=0)
        close_t = et.replace(hour=16, minute=0,  second=0, microsecond=0)
        return open_t <= et <= close_t
    except Exception:
        return False


def market_session_label() -> tuple[str, str]:
    try:
        from zoneinfo import ZoneInfo
        et = datetime.now(ZoneInfo("America/New_York"))
        if et.weekday() >= 5:
            return "🔴", "Market Closed (Weekend)"
        open_t  = et.replace(hour=9,  minute=30, second=0, microsecond=0)
        close_t = et.replace(hour=16, minute=0,  second=0, microsecond=0)
        pre_t   = et.replace(hour=4,  minute=0,  second=0, microsecond=0)
        after_t = et.replace(hour=20, minute=0,  second=0, microsecond=0)
        if open_t <= et <= close_t:
            return "🟢", "Market Open (US Regular Session)"
        if pre_t <= et < open_t:
            return "🟡", "Pre-Market (US)"
        if close_t < et <= after_t:
            return "🟡", "After-Hours (US)"
        return "🔴", "Market Closed (US)"
    except Exception:
        return "⚪", "Session Unknown"


# ── Session-state helpers ─────────────────────────────────────────────────────

def save_to_session(results: dict[str, "MarketData"]) -> None:
    """Persist ALL fetched MarketData (ok and failed) into Streamlit session state."""
    try:
        import streamlit as st
        existing: dict = st.session_state.get(_SESSION_CACHE_KEY, {})
        existing.update(results)          # store everything, including failures
        now_str = datetime.now().strftime("%H:%M:%S")
        _ep = time.time()
        st.session_state[_SESSION_CACHE_KEY]          = existing
        st.session_state[_SESSION_LAST_REFRESH_KEY]   = now_str
        st.session_state["mp_last_refresh_epoch"]     = _ep
        save_refresh_ts(_ep)          # persist so 60-min window survives restarts
    except Exception:
        pass


def get_from_session(ticker: str) -> Optional["MarketData"]:
    try:
        import streamlit as st
        cache: dict = st.session_state.get(_SESSION_CACHE_KEY, {})
        return cache.get(ticker.upper())
    except Exception:
        return None


def get_all_from_session() -> dict[str, "MarketData"]:
    try:
        import streamlit as st
        return dict(st.session_state.get(_SESSION_CACHE_KEY, {}))
    except Exception:
        return {}

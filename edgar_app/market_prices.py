"""
market_prices.py
----------------
Live market data fetching via yfinance with in-memory + session-state caching.

Design principles:
- Never crashes the app. Every public function returns a safe fallback.
- Does NOT overwrite manually-entered prices unless the caller explicitly
  decides to apply the fetched prices.
- 5-minute in-memory TTL cache shared across the process (fast repeated calls).
- Session-state cache mirrors the in-memory cache so the UI can inspect it.
- Bulk refresh uses a single yfinance.download() call for efficiency.
- Market-session awareness for US equities.
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

CACHE_TTL_SECONDS = 300          # 5 minutes
_SESSION_CACHE_KEY = "mp_price_cache"   # st.session_state key
_SESSION_LAST_REFRESH_KEY = "mp_last_refresh"

# ── In-process cache (thread-safe) ────────────────────────────────────────────

_cache: dict[str, tuple["MarketData", float]] = {}   # ticker → (data, ts)
_cache_lock = threading.Lock()


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class MarketData:
    """Live market snapshot for one ticker."""
    ticker:               str
    current_price:        Optional[float] = None
    previous_close:       Optional[float] = None
    daily_change_pct:     Optional[float] = None   # % change vs previous_close
    market_cap:           Optional[float] = None
    volume:               Optional[float] = None
    beta:                 Optional[float] = None
    currency:             str             = "USD"
    timestamp:            str             = ""     # ISO UTC
    error:                Optional[str]  = None    # set when fetch failed

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def is_ok(self) -> bool:
        return self.error is None and self.current_price is not None

    @property
    def day_indicator(self) -> str:
        """🟢 / 🔴 / ⚪ based on daily change."""
        if self.daily_change_pct is None:
            return "⚪"
        if self.daily_change_pct > 0:
            return "🟢"
        if self.daily_change_pct < 0:
            return "🔴"
        return "⚪"

    @property
    def change_str(self) -> str:
        if self.daily_change_pct is None:
            return "—"
        sign = "+" if self.daily_change_pct >= 0 else ""
        return f"{sign}{self.daily_change_pct:.2f}%"

    @property
    def price_str(self) -> str:
        if self.current_price is None:
            return "Market data unavailable"
        return f"{self.current_price:.2f} {self.currency}"


def _error_data(ticker: str, reason: str) -> MarketData:
    return MarketData(ticker=ticker, error=reason,
                      timestamp=datetime.now(timezone.utc).isoformat())


# ── Single-ticker fetch ────────────────────────────────────────────────────────

def get_market_data(ticker: str) -> MarketData:
    """
    Fetch live market data for *ticker*.

    Returns a MarketData object — check `.is_ok` or `.error` before using the
    price. Never raises; all errors are captured in `.error`.
    Caches results for CACHE_TTL_SECONDS in the process-level cache.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return _error_data(ticker, "Empty ticker")

    # Check in-process cache first
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(ticker)
        if cached and (now - cached[1]) < CACHE_TTL_SECONDS:
            return cached[0]

    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        fi = t.fast_info          # fast_info avoids downloading full history

        raw_price = getattr(fi, "last_price", None)
        raw_prev  = getattr(fi, "previous_close", None)
        raw_cap   = getattr(fi, "market_cap", None)
        raw_vol   = getattr(fi, "three_month_average_volume", None)
        raw_cur   = getattr(fi, "currency", "USD") or "USD"

        # current_price fallback chain
        price = None
        if raw_price and float(raw_price) > 0:
            price = float(raw_price)

        prev_close = float(raw_prev) if raw_prev and float(raw_prev) > 0 else None

        daily_chg: Optional[float] = None
        if price and prev_close and prev_close > 0:
            daily_chg = (price - prev_close) / prev_close * 100.0

        # Beta: only from .info to keep fast_info call cheap
        beta: Optional[float] = None
        try:
            info = t.info or {}
            raw_beta = info.get("beta")
            if raw_beta is not None:
                beta = float(raw_beta)
        except Exception:
            pass

        if price is None:
            data = _error_data(ticker, "No price returned — ticker may be delisted or invalid")
        else:
            data = MarketData(
                ticker        = ticker,
                current_price = price,
                previous_close= prev_close,
                daily_change_pct = daily_chg,
                market_cap    = float(raw_cap) if raw_cap else None,
                volume        = float(raw_vol) if raw_vol else None,
                beta          = beta,
                currency      = str(raw_cur),
                timestamp     = datetime.now(timezone.utc).isoformat(),
                error         = None,
            )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        # Friendly messages for common failure modes
        if "429" in msg or "rate" in msg.lower():
            msg = "Rate limit reached — try again in a few minutes"
        elif "no data" in msg.lower() or "empty" in msg.lower():
            msg = "No data available for this ticker"
        data = _error_data(ticker, msg)

    with _cache_lock:
        _cache[ticker] = (data, time.monotonic())

    return data


# ── Bulk refresh ──────────────────────────────────────────────────────────────

def refresh_all_prices(
    ticker_list: list[str],
    *,
    progress_callback=None,        # optional fn(done: int, total: int)
) -> dict[str, MarketData]:
    """
    Fetch live prices for all tickers in *ticker_list*.

    Uses a single yfinance.download() call for efficiency where possible,
    then falls back to individual Ticker() calls for tickers that failed.

    Returns dict[ticker → MarketData]. Never raises.
    """
    tickers = [t.strip().upper() for t in (ticker_list or []) if t.strip()]
    if not tickers:
        return {}

    results: dict[str, MarketData] = {}
    now = time.monotonic()

    # 1. Check cache for still-fresh entries
    fresh: set[str] = set()
    with _cache_lock:
        for t in tickers:
            cached = _cache.get(t)
            if cached and (now - cached[1]) < CACHE_TTL_SECONDS:
                results[t] = cached[0]
                fresh.add(t)

    stale = [t for t in tickers if t not in fresh]
    if not stale:
        return results

    # 2. Batch download via yfinance.download (period=1d for today's OHLCV)
    try:
        import yfinance as yf
        raw = yf.download(
            tickers   = stale,
            period    = "2d",           # 2 days to get today + prev close
            interval  = "1d",
            auto_adjust = True,
            progress  = False,
            threads   = True,
            timeout   = 20,
        )

        # yfinance returns multi-level columns when >1 ticker
        if len(stale) == 1:
            ticker = stale[0]
            close_col = "Close"
            try:
                closes = raw[close_col].dropna()
                price     = float(closes.iloc[-1]) if len(closes) >= 1 else None
                prev_cls  = float(closes.iloc[-2]) if len(closes) >= 2 else None
                daily_chg = ((price - prev_cls) / prev_cls * 100) if price and prev_cls else None
                data = MarketData(
                    ticker           = ticker,
                    current_price    = price,
                    previous_close   = prev_cls,
                    daily_change_pct = daily_chg,
                    currency         = "USD",
                    timestamp        = datetime.now(timezone.utc).isoformat(),
                )
            except Exception:
                data = _error_data(ticker, "Could not parse download data")
            results[ticker] = data
            with _cache_lock:
                _cache[ticker] = (data, now)
        else:
            # Multi-ticker: columns are (field, ticker)
            for ticker in stale:
                try:
                    closes = raw["Close"][ticker].dropna()
                    price    = float(closes.iloc[-1]) if len(closes) >= 1 else None
                    prev_cls = float(closes.iloc[-2]) if len(closes) >= 2 else None
                    daily_chg = ((price - prev_cls) / prev_cls * 100) if price and prev_cls else None
                    data = MarketData(
                        ticker           = ticker,
                        current_price    = price,
                        previous_close   = prev_cls,
                        daily_change_pct = daily_chg,
                        currency         = "USD",
                        timestamp        = datetime.now(timezone.utc).isoformat(),
                    )
                except Exception:
                    data = _error_data(ticker, "Could not parse download data")
                results[ticker] = data
                with _cache_lock:
                    _cache[ticker] = (data, now)

    except Exception as exc:  # noqa: BLE001
        # Batch failed — fall through to individual fetches
        for ticker in stale:
            if ticker not in results:
                data = get_market_data(ticker)
                results[ticker] = data
            if progress_callback:
                done = sum(1 for t in tickers if t in results)
                progress_callback(done, len(tickers))

    # 3. Individual fallback for tickers still missing
    missing = [t for t in stale if t not in results]
    for i, ticker in enumerate(missing):
        results[ticker] = get_market_data(ticker)
        if progress_callback:
            done = len(fresh) + len(stale) - len(missing) + i + 1
            progress_callback(done, len(tickers))

    return results


# ── Market session awareness ──────────────────────────────────────────────────

def is_us_market_open() -> bool:
    """Return True during approximate US regular market hours (9:30–16:00 ET)."""
    try:
        from zoneinfo import ZoneInfo
        et = datetime.now(ZoneInfo("America/New_York"))
        if et.weekday() >= 5:          # Saturday=5, Sunday=6
            return False
        open_time  = et.replace(hour=9,  minute=30, second=0, microsecond=0)
        close_time = et.replace(hour=16, minute=0,  second=0, microsecond=0)
        return open_time <= et <= close_time
    except Exception:
        return False


def market_session_label() -> tuple[str, str]:
    """Return (icon, label) describing the current market session."""
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
    """Persist fetched MarketData into Streamlit session state."""
    try:
        import streamlit as st
        existing: dict = st.session_state.get(_SESSION_CACHE_KEY, {})
        existing.update({t: d for t, d in results.items() if d.is_ok})
        st.session_state[_SESSION_CACHE_KEY] = existing
        st.session_state[_SESSION_LAST_REFRESH_KEY] = datetime.now().strftime("%H:%M:%S")
    except Exception:
        pass


def get_from_session(ticker: str) -> Optional["MarketData"]:
    """Retrieve last-fetched MarketData from session state (no TTL check)."""
    try:
        import streamlit as st
        cache: dict = st.session_state.get(_SESSION_CACHE_KEY, {})
        return cache.get(ticker.upper())
    except Exception:
        return None


def get_all_from_session() -> dict[str, "MarketData"]:
    """Return full session-state price cache."""
    try:
        import streamlit as st
        return dict(st.session_state.get(_SESSION_CACHE_KEY, {}))
    except Exception:
        return {}

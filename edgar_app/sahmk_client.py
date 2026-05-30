"""
sahmk_client.py
---------------
Market data provider for the Saudi market via the SAHMK API.

Official API:
  BASE_URL  = https://app.sahmk.sa/api/v1   (override via SAHMK_BASE_URL)
  Auth      = X-API-Key: <SAHMK_API_KEY>

MVP endpoint (free tier):
  GET /quote/{symbol}/   — single quote for a local-market symbol (e.g. "2222")

Configuration (environment variables):
  SAHMK_API_KEY   — required; your SAHMK subscription key
  SAHMK_BASE_URL  — optional; overrides the default base URL above

Design rules:
- Never raises. All public functions return None / empty dict on failure.
- Separate TTL cache per endpoint type (5 min quotes, 24 h everything else).
- Thread-safe via a single module-level lock.
- Zero dependency on yfinance or any other provider.
- Adding a new endpoint requires only a new _get() call + cache key.

Cache TTLs (seconds):
  QUOTES_TTL      = 300   (5 min)
  HISTORICAL_TTL  = 86400 (24 h)
  FINANCIAL_TTL   = 86400 (24 h)
  DIVIDENDS_TTL   = 86400 (24 h)
"""

from __future__ import annotations

import os
import time
import threading
import urllib.request
import urllib.error
import json as _json
from typing import Any, Optional

# ── Configuration ─────────────────────────────────────────────────────────────

_BASE_URL = os.environ.get("SAHMK_BASE_URL", "https://app.sahmk.sa/api/v1").rstrip("/")
_API_KEY  = os.environ.get("SAHMK_API_KEY", "")

# ── Cache TTLs ────────────────────────────────────────────────────────────────

QUOTES_TTL:     int = 300     # 5 minutes
HISTORICAL_TTL: int = 86_400  # 24 hours
FINANCIAL_TTL:  int = 86_400  # 24 hours
DIVIDENDS_TTL:  int = 86_400  # 24 hours

# ── In-process cache ──────────────────────────────────────────────────────────

_cache: dict[str, tuple[Any, float]] = {}
_lock  = threading.Lock()


def is_configured() -> bool:
    """Return True only if an API key is present in the environment."""
    return bool(os.environ.get("SAHMK_API_KEY", "").strip())


# ── Low-level HTTP helper ─────────────────────────────────────────────────────

def _get(path: str, params: dict | None = None, timeout: int = 10) -> Optional[dict | list]:
    """
    Execute a GET request against the SAHMK REST API.

    Returns the parsed JSON body on HTTP 200, or None on any failure
    (network error, non-200 status, JSON parse error, missing key).
    Never raises.
    """
    key = os.environ.get("SAHMK_API_KEY", "").strip()
    if not key:
        return None

    base = os.environ.get("SAHMK_BASE_URL", "https://app.sahmk.sa/api/v1").rstrip("/")
    url  = f"{base}/{path.lstrip('/')}"
    if params:
        qs  = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "X-API-Key":    key,
                "Accept":       "application/json",
                "User-Agent":   "Bousala/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return _json.loads(raw)
    except urllib.error.HTTPError as exc:
        # Surface rate-limit and auth errors without crashing
        if exc.code in (401, 403):
            _warn(f"SAHMK auth error {exc.code} — check SAHMK_API_KEY")
        elif exc.code == 429:
            try:
                _detail = _json.loads(exc.read().decode()).get("detail", "")
            except Exception:
                _detail = ""
            _warn(
                f"SAHMK rate limit exceeded — {_detail}"
                if _detail
                else "SAHMK rate limit exceeded — results from cache if available"
            )
        else:
            _warn(f"SAHMK HTTP {exc.code} for {path}")
        return None
    except Exception:
        return None


def _warn(msg: str) -> None:
    """Non-fatal warning — printed to stderr but never crashes the app."""
    import sys
    print(f"[sahmk_client] WARNING: {msg}", file=sys.stderr)


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_get(key: str, ttl: int) -> Optional[Any]:
    with _lock:
        entry = _cache.get(key)
        if entry and (time.monotonic() - entry[1]) < ttl:
            return entry[0]
    return None


def _cache_set(key: str, value: Any) -> None:
    with _lock:
        _cache[key] = (value, time.monotonic())


# ── Public API functions ──────────────────────────────────────────────────────

def get_quote(symbol: str, *, force: bool = False) -> Optional[dict]:
    """
    Retrieve the latest quote for *symbol* (local exchange symbol, e.g. "2222").

    Returns a dict with at least:
      { "symbol", "price", "change", "change_pct", "volume", "timestamp" }

    Returns None if the API is not configured, the symbol is unknown, or
    any network / parse error occurs.
    """
    symbol = (symbol or "").strip()
    if not symbol:
        return None
    cache_key = f"quote:{symbol}"
    if not force:
        cached = _cache_get(cache_key, QUOTES_TTL)
        if cached is not None:
            return cached

    # MVP free-tier endpoint: GET /quote/{symbol}/
    data = _get(f"quote/{symbol}/")
    result: Optional[dict] = None
    if isinstance(data, dict):
        # Normalise common field names across API versions
        price = _safe_float(
            data.get("price") or data.get("last_price") or data.get("lastPrice")
            or data.get("close") or data.get("current_price")
        )
        if price is not None:
            result = {
                "symbol":      symbol,
                "price":       price,
                "currency":    data.get("currency", "SAR"),
                "change":      _safe_float(data.get("change")),
                "change_pct":  _safe_float(
                    data.get("change_pct") or data.get("changePct") or data.get("pct_change")
                ),
                "volume":      _safe_float(data.get("volume")),
                "is_delayed":  bool(data.get("is_delayed", True)),
                "timestamp":   data.get("timestamp") or data.get("time") or "",
                "raw":         data,
            }

    if result is not None:
        _cache_set(cache_key, result)
    return result


def get_market_summary(*, force: bool = False) -> Optional[list]:
    """
    Retrieve a summary of Saudi market indices and top movers.

    Returns a list of dicts or None on failure.
    """
    cache_key = "market_summary"
    if not force:
        cached = _cache_get(cache_key, QUOTES_TTL)
        if cached is not None:
            return cached

    data = _get("market/summary")
    result = data if isinstance(data, list) else (
        data.get("data") or data.get("items") if isinstance(data, dict) else None
    )
    if result is not None:
        _cache_set(cache_key, result)
    return result


def get_historical(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
    *,
    force: bool = False,
) -> Optional[list]:
    """
    Retrieve historical OHLCV data for *symbol*.

    period   — e.g. "1d", "1w", "1m", "3m", "6m", "1y", "5y"
    interval — e.g. "1m", "5m", "1h", "1d", "1w"

    Returns a list of dicts: [{"date", "open", "high", "low", "close", "volume"}, ...]
    or None on failure.
    """
    symbol = (symbol or "").strip()
    if not symbol:
        return None
    cache_key = f"hist:{symbol}:{period}:{interval}"
    if not force:
        cached = _cache_get(cache_key, HISTORICAL_TTL)
        if cached is not None:
            return cached

    data = _get(f"historical/{symbol}", params={"period": period, "interval": interval})
    result = (
        data if isinstance(data, list)
        else data.get("data") or data.get("candles") if isinstance(data, dict)
        else None
    )
    if result is not None:
        _cache_set(cache_key, result)
    return result


def get_company_info(symbol: str, *, force: bool = False) -> Optional[dict]:
    """
    Retrieve company profile / fundamental information for *symbol*.

    Returns a dict or None on failure.
    """
    symbol = (symbol or "").strip()
    if not symbol:
        return None
    cache_key = f"info:{symbol}"
    if not force:
        cached = _cache_get(cache_key, FINANCIAL_TTL)
        if cached is not None:
            return cached

    data = _get(f"company/{symbol}/info")
    result = data if isinstance(data, dict) else None
    if result is not None:
        _cache_set(cache_key, result)
    return result


def get_financial_statements(symbol: str, *, force: bool = False) -> Optional[dict]:
    """
    Retrieve income statement, balance sheet, and cash flow for *symbol*.

    Returns a dict or None on failure.
    """
    symbol = (symbol or "").strip()
    if not symbol:
        return None
    cache_key = f"financials:{symbol}"
    if not force:
        cached = _cache_get(cache_key, FINANCIAL_TTL)
        if cached is not None:
            return cached

    data = _get(f"company/{symbol}/financials")
    result = data if isinstance(data, dict) else None
    if result is not None:
        _cache_set(cache_key, result)
    return result


def get_financial_ratios(symbol: str, *, force: bool = False) -> Optional[dict]:
    """
    Retrieve valuation ratios (P/E, P/B, EPS, ROE, etc.) for *symbol*.

    Returns a dict or None on failure.
    """
    symbol = (symbol or "").strip()
    if not symbol:
        return None
    cache_key = f"ratios:{symbol}"
    if not force:
        cached = _cache_get(cache_key, FINANCIAL_TTL)
        if cached is not None:
            return cached

    data = _get(f"company/{symbol}/ratios")
    result = data if isinstance(data, dict) else None
    if result is not None:
        _cache_set(cache_key, result)
    return result


def get_dividends(symbol: str, *, force: bool = False) -> Optional[list]:
    """
    Retrieve dividend history for *symbol*.

    Returns a list of dicts or None on failure.
    """
    symbol = (symbol or "").strip()
    if not symbol:
        return None
    cache_key = f"div:{symbol}"
    if not force:
        cached = _cache_get(cache_key, DIVIDENDS_TTL)
        if cached is not None:
            return cached

    data = _get(f"company/{symbol}/dividends")
    result = (
        data if isinstance(data, list)
        else data.get("data") or data.get("dividends") if isinstance(data, dict)
        else None
    )
    if result is not None:
        _cache_set(cache_key, result)
    return result


def get_market_events(*, force: bool = False) -> Optional[list]:
    """
    Retrieve upcoming market events (IPOs, rights issues, corporate actions).

    Returns a list of dicts or None on failure / not available on plan.
    """
    cache_key = "market_events"
    if not force:
        cached = _cache_get(cache_key, QUOTES_TTL)
        if cached is not None:
            return cached

    data = _get("market/events")
    result = (
        data if isinstance(data, list)
        else data.get("data") or data.get("events") if isinstance(data, dict)
        else None
    )
    if result is not None:
        _cache_set(cache_key, result)
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def clear_cache() -> None:
    """Remove all cached entries (useful for testing)."""
    with _lock:
        _cache.clear()


def cache_stats() -> dict:
    """Return a snapshot of the current cache state for diagnostics."""
    with _lock:
        now = time.monotonic()
        return {
            "entries": len(_cache),
            "keys":    list(_cache.keys()),
            "ages_s":  {k: round(now - v[1], 1) for k, v in _cache.items()},
        }

"""
ticker_validator.py
-------------------
Lightweight Yahoo Finance / yfinance ticker validation.

Probes yfinance in three stages (fast_info → info → history).
Never raises — all errors are captured in TickerValidation.error.

Typical usage (outside a Streamlit form so the network call is safe):

    from ticker_validator import validate_yahoo_ticker
    result = validate_yahoo_ticker("AAPL")
    if result.exists:
        print(result.company_name, result.current_price)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


# ── Asset type normalisation ──────────────────────────────────────────────────

_QUOTE_TYPE_MAP: dict[str, str] = {
    "EQUITY":       "Stock",
    "ETF":          "ETF",
    "MUTUALFUND":   "Fund",
    "FUTURE":       "Commodity",   # GC=F, SI=F, etc.
    "CURRENCY":     "Cash",        # XAUUSD=X, currency pairs
    "INDEX":        "Other",
    "CRYPTOCURRENCY": "Other",
    "OPTION":       "Other",
}


def _normalise_asset_type(quote_type: str) -> str:
    return _QUOTE_TYPE_MAP.get((quote_type or "").upper(), "Stock")


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class TickerValidation:
    """Complete result of a single ticker validation attempt."""
    ticker:           str            # original ticker entered by user
    resolved_ticker:  str  = ""     # ticker actually validated (may differ for Saudi)
    exists:           bool = False   # True if Yahoo Finance can price this ticker
    yahoo_linked:     bool = False   # alias for exists (clearer UI label)
    company_name:     str  = ""
    currency:         str  = ""      # e.g. "USD", "SAR"
    exchange:         str  = ""      # e.g. "NMS", "SAU", "CME"
    asset_type:       str  = ""      # normalised: Stock / ETF / Fund / Commodity / Cash / Other
    current_price:    float = 0.0
    price_source:     str  = ""      # "fast_info" | "info" | "history" | "unavailable"
    suggested_ticker: str  = ""      # non-empty when a Saudi shorthand was detected
    last_checked:     str  = ""      # ISO timestamp
    error:            str  = ""      # human-readable reason when exists=False


# ── Core validation ───────────────────────────────────────────────────────────

def validate_yahoo_ticker(ticker: str) -> TickerValidation:
    """
    Attempt to resolve *ticker* via yfinance using three probes.

    Probe priority:
      1. fast_info  — cheapest; gives price, currency, exchange
      2. info       — richer; gives name, quoteType; slower
      3. history    — final fallback; 5-day price history

    Safe for Saudi tickers (1120.SR, 2222.SR), futures (GC=F, SI=F),
    ETFs (GLD, IAU), and forex-quoted commodities (XAUUSD=X).
    """
    import yfinance as yf

    ticker = ticker.strip().upper()
    result = TickerValidation(
        ticker=ticker,
        resolved_ticker=ticker,
        last_checked=datetime.now().isoformat(),
    )

    if not ticker:
        result.error = "Empty ticker."
        return result

    try:
        yt = yf.Ticker(ticker)

        # ── Probe 1: fast_info ────────────────────────────────────────────
        try:
            fi = yt.fast_info
            price = (
                getattr(fi, "last_price", None)
                or getattr(fi, "regular_market_price", None)
            )
            if price is not None:
                price = float(price)
            if price and price > 0:
                result.exists        = True
                result.current_price = price
                result.price_source  = "fast_info"
                result.currency      = str(getattr(fi, "currency", "") or "")
                result.exchange      = str(getattr(fi, "exchange", "") or "")
        except Exception:
            pass

        # ── Probe 2: info dict ────────────────────────────────────────────
        try:
            info = yt.info or {}
            if info and isinstance(info, dict) and info.get("symbol"):
                result.exists = True
                result.company_name = (
                    info.get("shortName") or info.get("longName") or ""
                )
                if not result.currency:
                    result.currency = str(info.get("currency", "") or "")
                if not result.exchange:
                    result.exchange = str(info.get("exchange", "") or "")
                result.asset_type = _normalise_asset_type(
                    str(info.get("quoteType", ""))
                )
                # Use info price only as fallback if fast_info gave nothing
                if not result.current_price:
                    for key in (
                        "currentPrice",
                        "regularMarketPrice",
                        "previousClose",
                        "navPrice",
                    ):
                        p = info.get(key)
                        if p and float(p) > 0:
                            result.current_price = float(p)
                            result.price_source  = "info"
                            break
        except Exception:
            pass

        # ── Probe 3: recent history (last resort) ─────────────────────────
        if not result.exists:
            try:
                hist = yt.history(period="5d")
                if hist is not None and not hist.empty:
                    close = hist["Close"].dropna()
                    if len(close) > 0:
                        result.exists        = True
                        result.current_price = float(close.iloc[-1])
                        result.price_source  = "history"
            except Exception:
                pass

        if result.exists:
            result.yahoo_linked = True
            if not result.asset_type:
                result.asset_type = "Stock"   # safe default for plain equities
        else:
            result.error = (
                "No price data, company info, or recent history found on Yahoo Finance."
            )
            result.price_source = "unavailable"

    except Exception as exc:
        result.error = str(exc)[:300]
        result.price_source = "unavailable"

    return result


# ── Saudi shorthand detection ─────────────────────────────────────────────────

def suggest_saudi_ticker(raw: str) -> str | None:
    """
    If *raw* looks like a bare 4-digit Saudi stock code (e.g. "1120"),
    return the Yahoo Finance format "1120.SR".  Otherwise return None.
    """
    stripped = raw.strip()
    if stripped.isdigit() and len(stripped) == 4:
        return stripped + ".SR"
    return None

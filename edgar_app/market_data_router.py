"""
market_data_router.py
---------------------
Multi-provider pricing router for the Bousala portfolio app.

Priority chain (per holding):
  1. SAHMK  — if exchange_symbol (local_market_symbol) is set and key is configured
               Uses GET /quote/{symbol}/ on https://app.sahmk.sa/api/v1
  2. yfinance — ticker (yahoo_symbol, e.g. "2222.SR") via market_prices module
  3. cached  — last known price in the holding (price_source != "manual")
  4. manual  — user-entered current_price (always available as last resort)

Design rules:
- Never raises. All paths return a RoutedPrice (price may be None).
- Completely independent of the UI layer.
- Adding a new provider requires only a new step in get_routed_price().
- Provider name is always recorded so the UI can show the data source.
- RoutedPrice carries a normalised output compatible with the spec:
    { symbol, price, currency, source, updated_at, is_delayed }
"""

from __future__ import annotations

import datetime
import re as _re
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from portfolio.holdings import Holding


# ── Provider labels (internal codes) ─────────────────────────────────────────

PROVIDER_SAHMK    = "SAHMK"
PROVIDER_YFINANCE = "yfinance"
PROVIDER_CACHED   = "cached"
PROVIDER_MANUAL   = "manual"

# ── Display names for the UI / normalised output ───────────────────────────────

_DISPLAY = {
    PROVIDER_SAHMK:    "SAHMK",
    PROVIDER_YFINANCE: "Yahoo Finance",
    PROVIDER_CACHED:   "cached",
    PROVIDER_MANUAL:   "manual",
}


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class RoutedPrice:
    """
    Result of one routing decision.

    Normalised fields (populated when price is not None):
      symbol     — the symbol that was looked up
      price      — latest price
      currency   — price currency (e.g. "SAR", "USD")
      source     — display name of the provider ("SAHMK", "Yahoo Finance", …)
      updated_at — ISO-8601 timestamp of when the price was fetched
      is_delayed — True if the price is delayed (not real-time)
    """
    price:      Optional[float]          # None means all providers failed
    provider:   str                      # internal code: PROVIDER_* constant
    # --- normalised output fields ---
    symbol:     str            = ""
    currency:   str            = ""
    source:     str            = ""      # display name
    updated_at: str            = ""      # ISO-8601
    is_delayed: bool           = True
    change_pct: Optional[float] = None  # daily % change from provider (e.g. SAHMK)
    # --- diagnostics ---
    error:      Optional[str]  = None    # human-readable reason when price is None

    @property
    def is_ok(self) -> bool:
        return self.price is not None and self.price > 0


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Saudi symbol normalisation ────────────────────────────────────────────────

# Matches 4–5 digit Saudi tickers with an optional exchange suffix:
#   "2222"     → group(1) = "2222"
#   "2222.SE"  → group(1) = "2222"
#   "2222.SR"  → group(1) = "2222"
#   "2222.SA"  → group(1) = "2222"
_SAUDI_SYM_RE = _re.compile(r'^(\d{4,5})(?:\.[A-Za-z]{2,3})?$')


def _saudi_local_sym(exchange_symbol: str, ticker: str) -> str:
    """
    Return the clean local exchange symbol to pass to the SAHMK API.

    Priority:
      1. exchange_symbol — strip any .SE / .SR / .SA suffix
      2. ticker — if it looks like a Saudi ticker (4–5 digits + optional suffix)

    Returns "" when neither source resolves to a Saudi-looking symbol, so
    non-Saudi tickers (AAPL, MSFT, …) never trigger a SAHMK call.
    """
    for raw in (exchange_symbol, ticker):
        s = (raw or "").strip()
        if not s:
            continue
        m = _SAUDI_SYM_RE.match(s)
        if m:
            return m.group(1)   # numeric-only, e.g. "2222"
    return ""


# ── Core routing function ─────────────────────────────────────────────────────

def get_routed_price(
    ticker:            str,
    exchange_symbol:   str   = "",
    last_known_price:  float = 0.0,
    last_known_source: str   = "manual",
    *,
    force:         bool = False,
    sahmk_enabled: bool = True,
) -> RoutedPrice:
    """
    Return the best available price for *ticker* using the priority chain.

    Parameters
    ----------
    ticker            : Yahoo Finance / global ticker  (yahoo_symbol, e.g. "2222.SR")
    exchange_symbol   : Local exchange symbol          (local_market_symbol, e.g. "2222")
    last_known_price  : The holding's stored price (fallback)
    last_known_source : The holding's price_source string (to detect manual)
    force             : Bypass in-memory caches on all providers
    sahmk_enabled     : When False, skip SAHMK entirely and go straight to yfinance.
                        Also auto-appends .SR to bare 4-5 digit Saudi tickers so yfinance
                        can resolve them (e.g. "2222" → "2222.SR").
    """
    now = _now_iso()

    # ── Step 1: SAHMK — local_market_symbol → GET /quote/{symbol}/ ───────────
    # Normalise: strip .SE/.SR/.SA suffixes; fall back to ticker for bare Saudi codes
    local_sym = _saudi_local_sym(exchange_symbol, ticker)
    if sahmk_enabled and local_sym:
        try:
            import sahmk_client
            if sahmk_client.is_configured():
                quote = sahmk_client.get_quote(local_sym, force=force)
                if quote and isinstance(quote.get("price"), (int, float)):
                    p = float(quote["price"])
                    if p > 0:
                        return RoutedPrice(
                            price      = p,
                            provider   = PROVIDER_SAHMK,
                            symbol     = local_sym,
                            currency   = quote.get("currency", "SAR"),
                            source     = _DISPLAY[PROVIDER_SAHMK],
                            updated_at = quote.get("timestamp") or now,
                            is_delayed = bool(quote.get("is_delayed", True)),
                            change_pct = (
                                float(quote["change_pct"])
                                if isinstance(quote.get("change_pct"), (int, float))
                                else None
                            ),
                        )
        except Exception:
            pass

    # ── Step 2: yfinance — yahoo_symbol ───────────────────────────────────────
    # Always auto-suffix bare Saudi tickers (e.g. "2222" → "2222.SR") so yfinance
    # can resolve them on the Saudi exchange.  This applies both in Yahoo-only mode
    # AND as the fallback when SAHMK mode is active but SAHMK fails for a ticker
    # (e.g. Aramco 2222 returning no data) — without the suffix yfinance returns
    # a stale cached price and marks source = "cached".
    yahoo_sym = ticker.strip()
    if _re.match(r'^\d{4,5}$', yahoo_sym):
        yahoo_sym = yahoo_sym + ".SR"
    if yahoo_sym:
        try:
            from market_prices import get_market_data
            md = get_market_data(yahoo_sym, force=force)
            if md.is_ok and md.current_price and md.current_price > 0:
                return RoutedPrice(
                    price      = float(md.current_price),
                    provider   = PROVIDER_YFINANCE,
                    symbol     = yahoo_sym,
                    currency   = getattr(md, "currency", ""),
                    source     = _DISPLAY[PROVIDER_YFINANCE],
                    updated_at = now,
                    is_delayed = False,
                )
        except Exception:
            pass

    # ── Step 3: last cached price (any source that isn't "manual") ────────────
    if last_known_price and last_known_price > 0 and last_known_source != PROVIDER_MANUAL:
        return RoutedPrice(
            price      = float(last_known_price),
            provider   = PROVIDER_CACHED,
            symbol     = ticker or local_sym,
            currency   = "",
            source     = _DISPLAY[PROVIDER_CACHED],
            updated_at = now,
            is_delayed = True,
            error      = "Live fetch failed — using last cached price",
        )

    # ── Step 4: manual value ──────────────────────────────────────────────────
    if last_known_price and last_known_price > 0:
        return RoutedPrice(
            price      = float(last_known_price),
            provider   = PROVIDER_MANUAL,
            symbol     = ticker or local_sym,
            currency   = "",
            source     = _DISPLAY[PROVIDER_MANUAL],
            updated_at = now,
            is_delayed = True,
            error      = "Live fetch failed — using manual price",
        )

    return RoutedPrice(
        price    = None,
        provider = PROVIDER_MANUAL,
        symbol   = ticker or local_sym,
        source   = _DISPLAY[PROVIDER_MANUAL],
        error    = "No price available from any provider",
    )


# ── Bulk refresh for all holdings ─────────────────────────────────────────────

def refresh_holdings_prices(
    holdings: "dict[str, Holding]",
    *,
    force:         bool = False,
    sahmk_enabled: bool = True,
) -> "dict[str, RoutedPrice]":
    """
    Route prices for every holding in *holdings*.

    Returns dict[asset_id → RoutedPrice].
    Never raises; failed holdings get RoutedPrice(price=None).

    sahmk_enabled=False skips SAHMK entirely; bare Saudi tickers get .SR appended
    automatically so yfinance can resolve them.
    """
    results: dict[str, RoutedPrice] = {}
    for asset_id, h in holdings.items():
        try:
            routed = get_routed_price(
                ticker            = h.ticker,
                exchange_symbol   = getattr(h, "exchange_symbol", "") or "",
                last_known_price  = float(getattr(h, "current_price", 0.0) or 0.0),
                last_known_source = getattr(h, "price_source", "manual") or "manual",
                force             = force,
                sahmk_enabled     = sahmk_enabled,
            )
        except Exception as exc:
            routed = RoutedPrice(price=None, provider=PROVIDER_MANUAL, error=str(exc))
        results[asset_id] = routed
    return results

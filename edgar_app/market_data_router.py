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
    # --- diagnostics ---
    error:      Optional[str]  = None    # human-readable reason when price is None

    @property
    def is_ok(self) -> bool:
        return self.price is not None and self.price > 0


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Core routing function ─────────────────────────────────────────────────────

def get_routed_price(
    ticker:            str,
    exchange_symbol:   str   = "",
    last_known_price:  float = 0.0,
    last_known_source: str   = "manual",
    *,
    force: bool = False,
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
    """
    now = _now_iso()

    # ── Step 1: SAHMK — local_market_symbol → GET /quote/{symbol}/ ───────────
    local_sym = exchange_symbol.strip()
    if local_sym:
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
                        )
        except Exception:
            pass

    # ── Step 2: yfinance — yahoo_symbol ───────────────────────────────────────
    yahoo_sym = ticker.strip()
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
    force: bool = False,
) -> "dict[str, RoutedPrice]":
    """
    Route prices for every holding in *holdings*.

    Returns dict[original_ticker → RoutedPrice].
    Never raises; failed holdings get RoutedPrice(price=None).
    """
    results: dict[str, RoutedPrice] = {}
    for ticker, h in holdings.items():
        try:
            routed = get_routed_price(
                ticker            = ticker,
                exchange_symbol   = getattr(h, "exchange_symbol", "") or "",
                last_known_price  = float(getattr(h, "current_price", 0.0) or 0.0),
                last_known_source = getattr(h, "price_source", "manual") or "manual",
                force             = force,
            )
        except Exception as exc:
            routed = RoutedPrice(price=None, provider=PROVIDER_MANUAL, error=str(exc))
        results[ticker] = routed
    return results

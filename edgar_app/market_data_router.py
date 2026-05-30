"""
market_data_router.py
---------------------
Multi-provider pricing router for the Bousala portfolio app.

Priority chain (per holding):
  1. SAHMK  — if exchange_symbol is set and SAHMK_API_KEY is configured
  2. yfinance — existing market_prices.get_market_data() logic
  3. cached  — last known price already in the holding (price_source != "manual")
  4. manual  — user-entered current_price (always available as last resort)

Design rules:
- Never raises. All paths return a RoutedPrice (price may be None).
- Completely independent of the UI layer.
- Adding a new provider requires only a new step in get_routed_price().
- Provider name is always recorded so the UI can show the data source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from portfolio.holdings import Holding


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class RoutedPrice:
    """Result of one routing decision."""
    price:    Optional[float]   # None means all providers failed
    provider: str               # "SAHMK" | "yfinance" | "cached" | "manual"
    error:    Optional[str] = None   # human-readable reason when price is None

    @property
    def is_ok(self) -> bool:
        return self.price is not None and self.price > 0


# ── Provider labels ───────────────────────────────────────────────────────────

PROVIDER_SAHMK   = "SAHMK"
PROVIDER_YFINANCE = "yfinance"
PROVIDER_CACHED  = "cached"
PROVIDER_MANUAL  = "manual"


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
    ticker            : Yahoo Finance / global ticker (e.g. "2222.SR", "AAPL")
    exchange_symbol   : Local exchange symbol for regional providers (e.g. "2222")
    last_known_price  : The holding's current stored price (fallback)
    last_known_source : The holding's current price_source string (to detect manual)
    force             : Bypass in-memory caches on all providers
    """

    # ── Step 1: SAHMK (only if exchange_symbol is set and key is configured) ─
    if exchange_symbol.strip():
        try:
            import sahmk_client
            if sahmk_client.is_configured():
                quote = sahmk_client.get_quote(exchange_symbol.strip(), force=force)
                if quote and isinstance(quote.get("price"), (int, float)):
                    p = float(quote["price"])
                    if p > 0:
                        return RoutedPrice(price=p, provider=PROVIDER_SAHMK)
        except Exception:
            pass

    # ── Step 2: yfinance ──────────────────────────────────────────────────────
    if ticker.strip():
        try:
            from market_prices import get_market_data
            md = get_market_data(ticker.strip(), force=force)
            if md.is_ok and md.current_price and md.current_price > 0:
                return RoutedPrice(price=float(md.current_price), provider=PROVIDER_YFINANCE)
        except Exception:
            pass

    # ── Step 3: last cached price (any source that isn't "manual") ────────────
    if last_known_price and last_known_price > 0 and last_known_source != PROVIDER_MANUAL:
        return RoutedPrice(
            price=float(last_known_price),
            provider=PROVIDER_CACHED,
            error="Live fetch failed — using last cached price",
        )

    # ── Step 4: manual value ──────────────────────────────────────────────────
    if last_known_price and last_known_price > 0:
        return RoutedPrice(
            price=float(last_known_price),
            provider=PROVIDER_MANUAL,
            error="Live fetch failed — using manual price",
        )

    return RoutedPrice(
        price=None,
        provider=PROVIDER_MANUAL,
        error="No price available from any provider",
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

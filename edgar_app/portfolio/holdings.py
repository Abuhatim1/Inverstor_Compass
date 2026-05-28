"""
portfolio/holdings.py
---------------------
Actual Holdings + Transaction History.

This is the *real* portfolio (positions the user owns), separate from the
**Research Watchlist** (`PortfolioEntry` in `state.py`, populated automatically
whenever the user analyses a filing).

Storage is two JSON files alongside `portfolio_state.json`:
  · `holdings.json`     — { ticker: Holding }
  · `transactions.json` — [Transaction, ...] (append-only)

Derived metrics (market value, unrealized P&L, portfolio weight) are computed
on demand from `quantity`, `avg_cost`, and `current_price` — never persisted.

A BUY transaction updates the holding's `quantity` and `avg_cost` using
weighted-average cost. A SELL transaction reduces `quantity` (avg_cost stays
the same — that's how cost basis works). When quantity drops to zero, the
holding is kept with `quantity=0` so its metadata (market, sector) and
current_price survive in case the user re-buys; users can manually delete.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime


# ── Storage ───────────────────────────────────────────────────────────────────

_DIR              = os.path.dirname(__file__)
_HOLDINGS_FILE    = os.path.join(_DIR, "holdings.json")
_TRANSACTIONS_FILE = os.path.join(_DIR, "transactions.json")


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class Holding:
    """One actual position the user owns."""
    ticker:        str
    company_name:  str
    market:        str   = "US"        # "US" | "Saudi" | "Other"
    sector:        str   = "Other"
    quantity:      float = 0.0
    avg_cost:      float = 0.0         # weighted-average cost per share
    current_price: float = 0.0         # last manually-entered price
    added_at:      str   = ""          # ISO date

    # ── Derived metrics ──────────────────────────────────────────────────────
    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_cost

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.cost_basis <= 0:
            return 0.0
        return (self.unrealized_pnl / self.cost_basis) * 100.0


@dataclass
class Transaction:
    """One manual buy/sell record."""
    ticker:    str
    side:      str        # "BUY" | "SELL"
    quantity:  float
    price:     float
    date:      str        # ISO date
    notes:     str = ""
    recorded_at: str = ""  # ISO timestamp


# ── Holdings persistence ──────────────────────────────────────────────────────

def load_holdings() -> dict[str, Holding]:
    """Load holdings from disk; return empty dict on missing or corrupt file."""
    if not os.path.exists(_HOLDINGS_FILE):
        return {}
    try:
        with open(_HOLDINGS_FILE, "r", encoding="utf-8") as f:
            raw: dict = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    import dataclasses
    valid = {f.name for f in dataclasses.fields(Holding)}
    out: dict[str, Holding] = {}
    for ticker, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            filtered = {k: v for k, v in entry.items() if k in valid}
            out[ticker] = Holding(**filtered)
        except Exception:
            continue
    return out


def save_holdings(holdings: dict[str, Holding]) -> None:
    os.makedirs(_DIR, exist_ok=True)
    payload = {}
    for ticker, h in holdings.items():
        # Only serialize stored fields (not derived properties)
        payload[ticker] = asdict(h)
    with open(_HOLDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def upsert_holding(
    ticker:        str,
    company_name:  str | None = None,
    market:        str | None = None,
    sector:        str | None = None,
    quantity:      float | None = None,
    avg_cost:      float | None = None,
    current_price: float | None = None,
) -> Holding:
    """Insert or update one holding's fields. None means 'don't change'."""
    holdings = load_holdings()
    existing = holdings.get(ticker)
    new_holding = Holding(
        ticker=ticker,
        company_name=company_name if company_name is not None
                     else (existing.company_name if existing else ticker),
        market=market if market is not None
               else (existing.market if existing else "US"),
        sector=sector if sector is not None
               else (existing.sector if existing else "Other"),
        quantity=quantity if quantity is not None
                 else (existing.quantity if existing else 0.0),
        avg_cost=avg_cost if avg_cost is not None
                 else (existing.avg_cost if existing else 0.0),
        current_price=current_price if current_price is not None
                      else (existing.current_price if existing else 0.0),
        added_at=(existing.added_at if existing and existing.added_at
                  else date.today().isoformat()),
    )
    holdings[ticker] = new_holding
    save_holdings(holdings)
    return new_holding


def delete_holding(ticker: str) -> bool:
    holdings = load_holdings()
    if ticker in holdings:
        del holdings[ticker]
        save_holdings(holdings)
        return True
    return False


def update_current_price(ticker: str, price: float) -> bool:
    """Set the manually-entered current price for one holding."""
    holdings = load_holdings()
    if ticker not in holdings:
        return False
    holdings[ticker].current_price = float(price)
    save_holdings(holdings)
    return True


# ── Transactions persistence ──────────────────────────────────────────────────

def load_transactions() -> list[Transaction]:
    if not os.path.exists(_TRANSACTIONS_FILE):
        return []
    try:
        with open(_TRANSACTIONS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    import dataclasses
    valid = {f.name for f in dataclasses.fields(Transaction)}
    out: list[Transaction] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            filtered = {k: v for k, v in entry.items() if k in valid}
            out.append(Transaction(**filtered))
        except Exception:
            continue
    return out


def save_transactions(txns: list[Transaction]) -> None:
    os.makedirs(_DIR, exist_ok=True)
    with open(_TRANSACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump([asdict(t) for t in txns], f, indent=2, ensure_ascii=False)


def record_transaction(
    ticker:       str,
    side:         str,        # "BUY" | "SELL"
    quantity:     float,
    price:        float,
    txn_date:     str | None = None,
    notes:        str = "",
    company_name: str = "",
    market:       str = "US",
    sector:       str = "Other",
) -> tuple[Transaction, Holding | None, str | None]:
    """
    Record a buy/sell transaction AND update the corresponding holding.

    Returns (transaction, updated_holding, error_message).
    If error_message is not None, no state was changed.
    """
    side = side.upper()
    if side not in ("BUY", "SELL"):
        return None, None, f"Unknown transaction side: {side!r}"
    if quantity <= 0:
        return None, None, "Quantity must be greater than 0."
    if price < 0:
        return None, None, "Price must be 0 or greater."

    holdings = load_holdings()
    existing = holdings.get(ticker)

    if side == "SELL":
        if existing is None or existing.quantity <= 0:
            return None, None, f"Cannot SELL {ticker} — no position held."
        if quantity > existing.quantity + 1e-9:
            return None, None, (
                f"Cannot SELL {quantity} of {ticker} — only {existing.quantity} held."
            )
        new_qty = max(0.0, existing.quantity - quantity)
        # avg_cost unchanged on sell
        existing.quantity = new_qty
        # Keep current_price as-is (the sell price might be stale info)
        holdings[ticker] = existing
        updated = existing
    else:  # BUY
        if existing is None:
            updated = Holding(
                ticker=ticker,
                company_name=company_name or ticker,
                market=market,
                sector=sector,
                quantity=quantity,
                avg_cost=price,
                current_price=price,   # default current price to buy price
                added_at=date.today().isoformat(),
            )
        else:
            old_basis = existing.cost_basis
            buy_value = quantity * price
            new_qty = existing.quantity + quantity
            new_avg = (old_basis + buy_value) / new_qty if new_qty > 0 else 0.0
            existing.quantity = new_qty
            existing.avg_cost = new_avg
            if existing.current_price <= 0:
                existing.current_price = price
            updated = existing
        holdings[ticker] = updated

    save_holdings(holdings)

    # Append transaction
    txn = Transaction(
        ticker=ticker,
        side=side,
        quantity=float(quantity),
        price=float(price),
        date=txn_date or date.today().isoformat(),
        notes=notes,
        recorded_at=datetime.now().isoformat(),
    )
    txns = load_transactions()
    txns.append(txn)
    save_transactions(txns)
    return txn, updated, None


# ── Portfolio-level helpers ───────────────────────────────────────────────────

def total_market_value(holdings: dict[str, Holding]) -> float:
    return sum(h.market_value for h in holdings.values())


def total_cost_basis(holdings: dict[str, Holding]) -> float:
    return sum(h.cost_basis for h in holdings.values())


def portfolio_weights(holdings: dict[str, Holding]) -> dict[str, float]:
    """Return per-ticker weight % based on market value. Sums to 100% (or 0)."""
    total = total_market_value(holdings)
    if total <= 0:
        return {t: 0.0 for t in holdings}
    return {t: (h.market_value / total) * 100.0 for t, h in holdings.items()}

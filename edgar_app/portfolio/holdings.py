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

Holdings are fully independent from SEC / CIK. SEC linkage is optional and
only available for US-listed equities that have been analysed via Filing Search.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime


# ── Storage ───────────────────────────────────────────────────────────────────

_DIR              = os.path.dirname(__file__)
_HOLDINGS_FILE    = os.path.join(_DIR, "holdings.json")
_TRANSACTIONS_FILE = os.path.join(_DIR, "transactions.json")


# ── Taxonomy constants ────────────────────────────────────────────────────────

ASSET_TYPES: list[str] = [
    "Stock",
    "ETF",
    "Fund",
    "Commodity",
    "Gold",
    "Silver",
    "Cash",
    "Other",
]

CURRENCIES: list[str] = [
    "USD",
    "SAR",
    "EUR",
    "GBP",
    "AED",
    "KWD",
    "QAR",
    "CNY",
    "JPY",
    "Other",
]

# Asset type → broad risk class used by the Risk Engine
ASSET_RISK_CLASS: dict[str, str] = {
    "Stock":     "equity",
    "ETF":       "equity",
    "Fund":      "equity",
    "Commodity": "commodity",
    "Gold":      "commodity",
    "Silver":    "commodity",
    "Cash":      "currency",
    "Other":     "equity",
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class Holding:
    """One actual position the user owns."""
    ticker:        str
    company_name:  str
    market:        str   = "US"        # "US" | "Saudi" | "UK" | "Europe" | "Asia" | "Other"
    sector:        str   = "Other"
    quantity:      float = 0.0
    avg_cost:      float = 0.0         # weighted-average cost per share / unit
    current_price: float = 0.0         # last known price
    added_at:      str   = ""          # ISO date

    # ── Extended fields (v2 — backward-compatible defaults) ───────────────────
    asset_type:    str   = "Stock"     # from ASSET_TYPES
    currency:      str   = "USD"       # ISO currency code
    has_ticker:    bool  = True        # False for physical / unlisted assets (no yfinance)
    sec_linked:    bool  = False       # True if SEC CIK available / verified
    cik:           str   = ""          # SEC CIK when sec_linked
    purchase_date: str   = ""          # ISO date, optional
    notes:         str   = ""          # free-text notes
    price_source:       str   = "manual"    # "manual" | "yfinance" | "live"
    price_date:         str   = ""          # ISO date of last price update
    default_account_id: str   = ""          # linked investment account (optional)

    # ── Derived metrics ───────────────────────────────────────────────────────
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
    ticker:      str
    side:        str        # "BUY" | "SELL"
    quantity:    float
    price:       float
    date:        str        # ISO date
    notes:       str  = ""
    recorded_at: str  = ""  # ISO timestamp
    account_id:  str  = ""  # linked investment account (optional)
    fees:        float = 0.0  # broker/custody fees


# ── Holdings persistence ──────────────────────────────────────────────────────

def load_holdings() -> dict[str, "Holding"]:
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


def save_holdings(holdings: dict[str, "Holding"]) -> None:
    os.makedirs(_DIR, exist_ok=True)
    payload = {}
    for ticker, h in holdings.items():
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
    # Extended fields
    asset_type:    str | None = None,
    currency:      str | None = None,
    has_ticker:    bool | None = None,
    sec_linked:    bool | None = None,
    cik:           str | None = None,
    purchase_date: str | None = None,
    notes:         str | None = None,
    price_source:  str | None = None,
    price_date:    str | None = None,
) -> "Holding":
    """Insert or update one holding's fields. None means 'don't change'."""
    holdings = load_holdings()
    existing = holdings.get(ticker)

    def _pick(new, old_attr: str, default):
        if new is not None:
            return new
        return getattr(existing, old_attr) if existing else default

    new_holding = Holding(
        ticker=ticker,
        company_name=_pick(company_name, "company_name", ticker),
        market=_pick(market, "market", "US"),
        sector=_pick(sector, "sector", "Other"),
        quantity=_pick(quantity, "quantity", 0.0),
        avg_cost=_pick(avg_cost, "avg_cost", 0.0),
        current_price=_pick(current_price, "current_price", 0.0),
        added_at=(existing.added_at if existing and existing.added_at
                  else date.today().isoformat()),
        asset_type=_pick(asset_type, "asset_type", "Stock"),
        currency=_pick(currency, "currency", "USD"),
        has_ticker=_pick(has_ticker, "has_ticker", True),
        sec_linked=_pick(sec_linked, "sec_linked", False),
        cik=_pick(cik, "cik", ""),
        purchase_date=_pick(purchase_date, "purchase_date", ""),
        notes=_pick(notes, "notes", ""),
        price_source=_pick(price_source, "price_source", "manual"),
        price_date=_pick(price_date, "price_date", ""),
    )
    holdings[ticker] = new_holding
    save_holdings(holdings)
    return new_holding


def delete_holding(ticker: str) -> bool:
    """Hard delete — removes the holding with no backup."""
    holdings = load_holdings()
    if ticker in holdings:
        del holdings[ticker]
        save_holdings(holdings)
        return True
    return False


_DELETED_HOLDINGS_FILE = os.path.join(_DIR, "deleted_holdings.json")


def soft_delete_holding(ticker: str) -> bool:
    """
    Remove a holding from holdings.json and archive it in deleted_holdings.json
    with a deletion timestamp.

    Returns True if the holding existed and was removed, False otherwise.
    Does NOT touch Research Watchlist, thesis data, or transaction history.
    """
    holdings = load_holdings()
    if ticker not in holdings:
        return False

    # ── Archive ───────────────────────────────────────────────────────────────
    try:
        if os.path.exists(_DELETED_HOLDINGS_FILE):
            with open(_DELETED_HOLDINGS_FILE, "r", encoding="utf-8") as f:
                archive: list = json.load(f)
            if not isinstance(archive, list):
                archive = []
        else:
            archive = []
    except (json.JSONDecodeError, OSError):
        archive = []

    entry = asdict(holdings[ticker])
    entry["_deleted_at"]       = datetime.now().isoformat()
    entry["_original_ticker"]  = ticker
    archive.append(entry)

    os.makedirs(_DIR, exist_ok=True)
    with open(_DELETED_HOLDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)

    # ── Remove from live holdings ─────────────────────────────────────────────
    del holdings[ticker]
    save_holdings(holdings)
    return True


def update_current_price(ticker: str, price: float, source: str = "manual") -> bool:
    """Set the current price for one holding, with optional source label."""
    holdings = load_holdings()
    if ticker not in holdings:
        return False
    holdings[ticker].current_price = float(price)
    holdings[ticker].price_source  = source
    holdings[ticker].price_date    = date.today().isoformat()
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
    # Extended fields — used when a BUY creates a new holding
    asset_type:   str = "Stock",
    currency:     str = "USD",
    has_ticker:   bool = True,
    sec_linked:   bool = False,
    account_id:   str = "",
    fees:         float = 0.0,
) -> tuple["Transaction", "Holding | None", "str | None"]:
    """
    Record a buy/sell transaction AND update the corresponding holding.

    Returns (transaction, updated_holding, error_message).
    If error_message is not None, no state was changed.
    On SELL, also creates FIFO closed lots via closed_holdings.execute_sell_fifo.
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
    sell_date = txn_date or date.today().isoformat()

    if side == "SELL":
        if existing is None or existing.quantity <= 0:
            return None, None, f"Cannot SELL {ticker} — no position held."
        if quantity > existing.quantity + 1e-9:
            return None, None, (
                f"Cannot SELL {quantity} of {ticker} — only {existing.quantity} held."
            )
        # Run FIFO engine first (validation step — does not write)
        from .closed_holdings import execute_sell_fifo, append_closed_lots
        _cn   = getattr(existing, "company_name", ticker) or company_name or ticker
        _cur  = getattr(existing, "currency", currency) or currency
        _aid  = account_id or getattr(existing, "default_account_id", "")
        closed_lots, fifo_err = execute_sell_fifo(
            ticker=ticker, company_name=_cn, currency=_cur,
            quantity=float(quantity), sell_price=float(price),
            sell_date=sell_date, account_id=_aid,
            fees=float(fees), notes=notes,
        )
        if fifo_err:
            return None, None, fifo_err

        new_qty = max(0.0, existing.quantity - quantity)
        existing.quantity = new_qty
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
                current_price=price,
                added_at=date.today().isoformat(),
                asset_type=asset_type,
                currency=currency,
                has_ticker=has_ticker,
                sec_linked=sec_linked,
                price_source="manual",
                price_date=date.today().isoformat(),
                default_account_id=account_id,
            )
        else:
            old_basis = existing.cost_basis
            buy_value = quantity * price
            new_qty   = existing.quantity + quantity
            new_avg   = (old_basis + buy_value) / new_qty if new_qty > 0 else 0.0
            existing.quantity  = new_qty
            existing.avg_cost  = new_avg
            if existing.current_price <= 0:
                existing.current_price = price
            updated = existing
        holdings[ticker] = updated

    save_holdings(holdings)

    txn = Transaction(
        ticker=ticker,
        side=side,
        quantity=float(quantity),
        price=float(price),
        date=sell_date,
        notes=notes,
        recorded_at=datetime.now().isoformat(),
        account_id=account_id,
        fees=float(fees),
    )
    txns = load_transactions()
    txns.append(txn)
    save_transactions(txns)

    # Persist FIFO closed lots (only for SELL; variable defined above)
    if side == "SELL" and closed_lots:
        for lot in closed_lots:
            lot.sell_txn_id = txn.recorded_at
        append_closed_lots(closed_lots)

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

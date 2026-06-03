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
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime


# ── Storage ───────────────────────────────────────────────────────────────────

_DIR               = os.path.dirname(__file__)
_HOLDINGS_FILE     = os.path.join(_DIR, "holdings.json")
_TRANSACTIONS_FILE = os.path.join(_DIR, "transactions.json")
_COUNTER_FILE      = os.path.join(_DIR, "_asset_counter.json")


# ── Asset-ID generation ───────────────────────────────────────────────────────

_AST_ID_PAT = re.compile(r'^AST_\d{6}$')


def _scan_max_asset_num() -> int:
    """Scan holdings.json for the highest AST_NNNNNN sequence number.
    Used to seed the counter when the counter file is absent."""
    try:
        if not os.path.exists(_HOLDINGS_FILE):
            return 0
        with open(_HOLDINGS_FILE, "r", encoding="utf-8") as _f:
            raw = json.load(_f)
        max_num = 0
        for key in raw:
            if _AST_ID_PAT.match(str(key)):
                max_num = max(max_num, int(str(key)[4:]))
        return max_num
    except Exception:
        return 0


def _gen_asset_id() -> str:
    """Generate a sequential asset identifier in AST_NNNNNN format.
    Counter is persisted in _asset_counter.json next to holdings.json."""
    try:
        if os.path.exists(_COUNTER_FILE):
            with open(_COUNTER_FILE, "r", encoding="utf-8") as _cf:
                next_num = int(json.load(_cf).get("next", 1))
        else:
            next_num = _scan_max_asset_num() + 1
    except Exception:
        next_num = 1
    asset_id = f"AST_{next_num:06d}"
    try:
        os.makedirs(_DIR or ".", exist_ok=True)
        from portfolio._io import atomic_json_write
        atomic_json_write(_COUNTER_FILE, {"next": next_num + 1})
    except Exception:
        pass
    return asset_id


# ── Ticker normalisation ───────────────────────────────────────────────────────

def normalize_ticker(ticker: str) -> str:
    """
    Normalise a ticker symbol for consistent storage and lookup.

    Rules applied:
    · Strip whitespace.
    · Saudi Exchange: replace the invalid .SE suffix with .SR
      (Yahoo Finance uses .SR; .SE is the Stockholm exchange).
      e.g. 2222.SE → 2222.SR, 1120.SE → 1120.SR
    """
    t = ticker.strip()
    if t.upper().endswith(".SE"):
        return t[:-3] + ".SR"
    return t


def _check_new_holding_account(existing: "Holding | None", account_id: str) -> str | None:
    """
    Return an error string when a *new* holding would be created without an
    account_id, else return None.

    Called by both record_transaction() (BUY path) and upsert_holding()
    so the rule is enforced at every creation path.
    """
    if existing is None and not account_id:
        return "Account is required when opening a new position."
    return None


# ── Taxonomy constants ────────────────────────────────────────────────────────

ASSET_TYPES: list[str] = [
    "Stock",
    "ETF",
    "REIT",
    "Mutual Fund",
    "Sukuk",
    "Bond",
    "Cash",
    "Precious Metal",
    "Commodity",
    "Real Estate",
    "Private Equity",
    "Private Asset",
    "Crypto",
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
    "Stock":          "equity",
    "ETF":            "equity",
    "REIT":           "equity",
    "Mutual Fund":    "equity",
    "Sukuk":          "fixed_income",
    "Bond":           "fixed_income",
    "Cash":           "currency",
    "Precious Metal": "commodity",
    "Commodity":      "commodity",
    "Real Estate":    "real_estate",
    "Private Equity": "private",
    "Private Asset":  "private",
    "Crypto":         "crypto",
    "Other":          "equity",
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class Holding:
    """One actual position the user owns."""
    ticker:        str
    company_name:  str
    asset_id:      str   = ""          # unique asset identifier (8-char UUID); generated at creation
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
    price_source:       str   = "manual"    # "manual" | "yfinance" | "SAHMK" | "cached"
    price_date:         str   = ""          # ISO date of last price update
    default_account_id: str   = ""          # linked investment account (optional)

    # ── Market-provider fields (v3 — backward-compatible defaults) ─────────
    exchange_symbol: str  = ""          # Local exchange symbol for regional providers
                                        # e.g. Saudi Aramco → "2222", Al Rajhi → "1120"
                                        # Provider-agnostic: reused across SAHMK, future GCC

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
    ticker:         str
    side:           str         # "BUY" | "SELL"
    quantity:       float
    price:          float
    date:           str         # ISO date
    notes:          str   = ""
    recorded_at:    str   = ""  # ISO timestamp
    account_id:     str   = ""  # linked investment account (optional)
    fees:           float = 0.0
    transaction_id:      str   = ""  # immutable; auto-generated at creation
    asset_id:            str   = ""  # links to Holding.asset_id
    # Settlement-only fields (default empty/zero so existing records load unchanged)
    settlement_amount:   float = 0.0  # positive = income, negative = expense
    settlement_category: str   = ""   # from SETTLEMENT_CATEGORIES
    settlement_currency: str   = ""   # ISO currency code


# Settlement categories (exhaustive list — do not extend without updating tests)
SETTLEMENT_CATEGORIES: list[str] = [
    "Dividend",
    "Fee",
    "Tax",
    "Zakat",
    "Islamic Purification",
    "Adjustment",
]

# Cash-ledger type mapping for each settlement category
_SETTLE_LEDGER_TYPE: dict[str, str] = {
    "Dividend":           "DIVIDEND",
    "Fee":                "FEE",
    "Tax":                "FEE",
    "Zakat":              "FEE",
    "Islamic Purification":"FEE",
    "Adjustment":         "OTHER",
}


# ── Holdings persistence ──────────────────────────────────────────────────────

def load_holdings(path: str | None = None) -> dict[str, "Holding"]:
    """
    Load holdings from disk, keyed by asset_id.

    Backward-compatible migration: old holdings.json files were keyed by ticker
    with no asset_id field.  On first load those entries are transparently migrated
    — a fresh 8-char asset_id is generated so the dict is consistently UUID-keyed.
    Migrated data is written back to disk automatically (production path only).

    Pass *path* to target a specific file (useful in tests).
    """
    filepath = path or _HOLDINGS_FILE
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw: dict = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    import dataclasses
    valid = {f.name for f in dataclasses.fields(Holding)}
    out: dict[str, Holding] = {}
    needs_resave = False
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            filtered = {k: v for k, v in entry.items() if k in valid}
            # ── Backward-compatible migration ──────────────────────────────────
            # Old formats: ticker-keyed (no asset_id), or 8-char UUID asset_id.
            # Current format: AST_NNNNNN sequential key.
            existing_id = filtered.get("asset_id", "")
            if not existing_id or not _AST_ID_PAT.match(existing_id):
                # Missing, old ticker-string, or old 8-char UUID — generate new ID
                filtered["asset_id"] = _gen_asset_id()
                needs_resave = True
            holding = Holding(**filtered)
            out[holding.asset_id] = holding
        except Exception:
            continue
    # Write migrated data back only for the real file (not test temp paths)
    if needs_resave and path is None:
        save_holdings(out)
    return out


def save_holdings(holdings: dict[str, "Holding"], path: str | None = None) -> None:
    """Save holdings to disk, keyed by asset_id.  Pass *path* to override default file."""
    from portfolio._io import atomic_json_write
    filepath = path or _HOLDINGS_FILE
    payload = {asset_id: asdict(h) for asset_id, h in holdings.items()}
    atomic_json_write(filepath, payload)


def upsert_holding(
    ticker:          str = "",
    asset_id:        str | None = None,    # supply to target a specific holding by asset_id
    company_name:    str | None = None,
    market:          str | None = None,
    sector:          str | None = None,
    quantity:        float | None = None,
    avg_cost:        float | None = None,
    current_price:   float | None = None,
    # Extended fields
    asset_type:      str | None = None,
    currency:        str | None = None,
    has_ticker:      bool | None = None,
    sec_linked:      bool | None = None,
    cik:             str | None = None,
    purchase_date:   str | None = None,
    notes:           str | None = None,
    price_source:    str | None = None,
    price_date:      str | None = None,
    # Account linkage — mandatory when creating a NEW holding
    default_account_id: str | None = None,
    # v3 market-provider fields
    exchange_symbol: str | None = None,
    # Optional: override storage path (useful in tests)
    path:            str | None = None,
) -> "Holding":
    """
    Insert or update one holding's fields.  None means 'don't change'.

    Lookup order:
    1. If *asset_id* is provided, look up the holding by that asset_id directly.
    2. Otherwise scan holdings for the first entry whose .ticker matches *ticker*
       (open position — qty > 0 — preferred, then any match).  This preserves
       backward-compatible behaviour for callers that don't yet have an asset_id.
    3. If no existing holding is found, a new one is created with a freshly
       generated asset_id.

    A new holding requires *default_account_id*; updates may omit it.
    Pass *path* to target a specific file (useful in tests).
    """
    holdings = load_holdings(path=path)

    # ── Locate existing holding ────────────────────────────────────────────────
    if asset_id:
        existing = holdings.get(asset_id)
    elif ticker:
        existing = next(
            (h for h in holdings.values()
             if h.ticker == ticker and h.quantity > 1e-9),
            None,
        ) or next(
            (h for h in holdings.values() if h.ticker == ticker),
            None,
        )
    else:
        existing = None

    # ── Effective identifiers ──────────────────────────────────────────────────
    _eff_asset_id = (existing.asset_id if existing
                     else (asset_id or _gen_asset_id()))
    _eff_ticker   = ticker or (existing.ticker if existing else "UNKNOWN")

    def _pick(new, old_attr: str, default):
        if new is not None:
            return new
        return getattr(existing, old_attr) if existing else default

    # ── Account-linkage enforcement ────────────────────────────────────────────
    _eff_aid = _pick(default_account_id, "default_account_id", "")
    err = _check_new_holding_account(existing, _eff_aid)
    if err:
        raise ValueError(err)

    new_holding = Holding(
        ticker=_eff_ticker,
        asset_id=_eff_asset_id,
        company_name=_pick(company_name, "company_name", _eff_ticker),
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
        default_account_id=_eff_aid,
        exchange_symbol=_pick(exchange_symbol, "exchange_symbol", ""),
    )
    holdings[_eff_asset_id] = new_holding
    save_holdings(holdings, path=path)
    return new_holding


def delete_holding(asset_id: str) -> bool:
    """Hard delete — removes the holding with no backup."""
    holdings = load_holdings()
    if asset_id in holdings:
        del holdings[asset_id]
        save_holdings(holdings)
        return True
    return False


_DELETED_HOLDINGS_FILE = os.path.join(_DIR, "deleted_holdings.json")


def soft_delete_holding(asset_id: str) -> bool:
    """
    Remove a holding from holdings.json and archive it in deleted_holdings.json
    with a deletion timestamp.

    Returns True if the holding existed and was removed, False otherwise.
    Does NOT touch Research Watchlist, thesis data, or transaction history.
    """
    holdings = load_holdings()
    if asset_id not in holdings:
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

    entry = asdict(holdings[asset_id])
    entry["_deleted_at"]       = datetime.now().isoformat()
    entry["_original_asset_id"] = asset_id
    archive.append(entry)

    from portfolio._io import atomic_json_write
    atomic_json_write(_DELETED_HOLDINGS_FILE, archive)

    # ── Remove from live holdings ─────────────────────────────────────────────
    del holdings[asset_id]
    save_holdings(holdings)
    return True


def update_current_price(
    asset_id: str,
    price: float,
    source: str = "manual",
    path: str | None = None,
) -> bool:
    """Update the stored current_price for the holding identified by *asset_id*.

    Pass *path* to target a specific file (useful in tests).
    Returns True if the holding was found and updated.
    """
    holdings = load_holdings(path=path)
    if asset_id not in holdings:
        return False
    holdings[asset_id].current_price = float(price)
    holdings[asset_id].price_source  = source
    holdings[asset_id].price_date    = date.today().isoformat()
    save_holdings(holdings, path=path)
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
            # Back-fill transaction_id for old records that pre-date the field
            if not filtered.get("transaction_id"):
                filtered["transaction_id"] = "TXN_" + str(uuid.uuid4())[:8]
            out.append(Transaction(**filtered))
        except Exception:
            continue
    return out


def save_transactions(txns: list[Transaction]) -> None:
    from portfolio._io import atomic_json_write
    atomic_json_write(_TRANSACTIONS_FILE, [asdict(t) for t in txns])


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
    # Optional: supply to target a specific holding (bypasses ticker scan)
    asset_id:     str | None = None,
) -> tuple["Transaction", "Holding | None", "str | None"]:
    """
    Record a buy/sell transaction AND update the corresponding holding.

    Returns (transaction, updated_holding, error_message).
    If error_message is not None, no state was changed.
    On SELL, also creates FIFO closed lots via closed_holdings.execute_sell_fifo.

    Lookup order for the target holding:
    1. If *asset_id* is given, look up holdings[asset_id] directly.
    2. Otherwise scan for the first holding with h.ticker == ticker
       (open position — qty > 0 — preferred, then any match).
    3. If no existing holding is found on BUY, a new one is created.
    """
    ticker    = normalize_ticker(ticker)
    side      = side.upper()
    if side not in ("BUY", "SELL"):
        return None, None, f"Unknown transaction side: {side!r}"
    if quantity <= 0:
        return None, None, "Quantity must be greater than 0."
    if price < 0:
        return None, None, "Price must be 0 or greater."

    holdings = load_holdings()

    # ── Locate target holding ──────────────────────────────────────────────────
    if asset_id:
        existing = holdings.get(asset_id)
    else:
        existing = next(
            (h for h in holdings.values()
             if h.ticker == ticker and h.quantity > 1e-9),
            None,
        ) or next(
            (h for h in holdings.values() if h.ticker == ticker),
            None,
        )

    _eff_asset_id = (existing.asset_id if existing
                     else (asset_id or _gen_asset_id()))
    sell_date = txn_date or date.today().isoformat()

    if side == "SELL":
        if existing is None or existing.quantity <= 0:
            return None, None, f"Cannot SELL {ticker} — no position held."
        if quantity > existing.quantity + 1e-9:
            return None, None, (
                f"Cannot sell {quantity:,.4f} of {ticker} — "
                f"only {existing.quantity:,.4f} shares held."
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
            # Fallback for holdings not created via BUY transactions:
            fallback_avg_cost=float(existing.avg_cost),
            fallback_open_date=getattr(existing, "added_at", "") or sell_date,
        )
        if fifo_err:
            return None, None, fifo_err

        new_qty = max(0.0, existing.quantity - quantity)
        existing.quantity = new_qty
        holdings[_eff_asset_id] = existing
        updated = existing
    else:  # BUY
        _acct_err = _check_new_holding_account(existing, account_id)
        if _acct_err:
            return None, None, _acct_err
        if existing is None:
            updated = Holding(
                ticker=ticker,
                asset_id=_eff_asset_id,
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
        holdings[_eff_asset_id] = updated

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
        transaction_id="TXN_" + str(uuid.uuid4())[:8],
        asset_id=_eff_asset_id,
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
    """Return per-asset_id weight % based on market value. Sums to 100% (or 0)."""
    total = total_market_value(holdings)
    if total <= 0:
        return {aid: 0.0 for aid in holdings}
    return {aid: (h.market_value / total) * 100.0 for aid, h in holdings.items()}


# ── Settlement engine ─────────────────────────────────────────────────────────

def record_settlement(
    amount:          float,
    category:        str,
    currency:        str,
    settlement_date: str | None = None,
    notes:           str = "",
    asset_id:        str = "",
    account_id:      str = "",
) -> "tuple[Transaction | None, str | None]":
    """
    Record a settlement (dividend, fee, tax, zakat, purification, adjustment).

    Three-step atomic write:
      1. Append SETTLEMENT Transaction to transactions.json
      2. Append CashEntry to cash_ledger.json  (only when account_id provided)
      3. Update Account.cash_balance            (only when account_id provided)

    Returns (transaction, None) on success, (None, error_message) on failure.
    NEVER modifies quantity, avg_cost, cost_basis, or FIFO lots.
    """
    if amount == 0.0:
        return None, "Amount must not be zero."
    if category not in SETTLEMENT_CATEGORIES:
        return None, (
            f"Invalid category {category!r}. "
            f"Must be one of: {', '.join(SETTLEMENT_CATEGORIES)}."
        )
    if len(notes.strip()) < 10:
        return None, "Notes must be at least 10 characters."

    ticker = ""
    if asset_id:
        h = load_holdings().get(asset_id)
        if h is None:
            return None, f"Holding {asset_id!r} not found."
        ticker = h.ticker

    if account_id:
        from portfolio.accounts import load_accounts as _la
        if account_id not in _la():
            return None, f"Account {account_id!r} not found."

    # Step 1 — append transaction
    txn = Transaction(
        ticker=ticker,
        side="SETTLEMENT",
        quantity=0.0,
        price=0.0,
        date=settlement_date or date.today().isoformat(),
        notes=notes,
        recorded_at=datetime.now().isoformat(),
        account_id=account_id,
        fees=0.0,
        transaction_id="TXN_" + str(uuid.uuid4())[:8],
        asset_id=asset_id,
        settlement_amount=amount,
        settlement_category=category,
        settlement_currency=currency,
    )
    txns = load_transactions()
    txns.append(txn)
    save_transactions(txns)

    # Steps 2 & 3 — cash effects
    if account_id:
        from portfolio.cash_ledger import append_cash_entry as _ace
        from portfolio.accounts import update_account_cash as _uac
        _ace(
            account_id=account_id,
            transaction_type=_SETTLE_LEDGER_TYPE.get(category, "OTHER"),
            currency=currency,
            amount=amount,
            linked_ticker=ticker,
            notes=notes,
        )
        _uac(account_id, amount)

    return txn, None


def edit_settlement(
    transaction_id:  str,
    amount:          float | None = None,
    category:        str | None = None,
    currency:        str | None = None,
    settlement_date: str | None = None,
    notes:           str | None = None,
    asset_id:        str | None = None,
    account_id:      str | None = None,
) -> "tuple[Transaction | None, str | None]":
    """
    Edit an existing settlement.

    Old cash effects are reversed via a negating cash-ledger entry (audit
    trail preserved).  New cash effects are then posted.

    Returns (updated_transaction, None) on success, (None, error_msg) on failure.
    """
    txns = load_transactions()
    idx = next(
        (i for i, t in enumerate(txns) if t.transaction_id == transaction_id),
        None,
    )
    if idx is None:
        return None, f"Transaction {transaction_id!r} not found."
    orig = txns[idx]
    if orig.side != "SETTLEMENT":
        return None, f"Transaction {transaction_id!r} is not a SETTLEMENT."

    # Resolve new field values (keep original if not provided)
    new_amount   = amount          if amount   is not None else orig.settlement_amount
    new_category = category        if category is not None else orig.settlement_category
    new_currency = currency        if currency is not None else orig.settlement_currency
    new_date     = settlement_date if settlement_date is not None else orig.date
    new_notes    = notes           if notes    is not None else orig.notes
    new_asset_id = asset_id        if asset_id is not None else orig.asset_id
    new_acct_id  = account_id      if account_id is not None else orig.account_id

    if new_amount == 0.0:
        return None, "Amount must not be zero."
    if new_category not in SETTLEMENT_CATEGORIES:
        return None, f"Invalid category {new_category!r}."
    if len(new_notes.strip()) < 10:
        return None, "Notes must be at least 10 characters."

    # Resolve ticker for (possibly changed) asset_id
    new_ticker = orig.ticker
    if asset_id is not None:
        if new_asset_id:
            h = load_holdings().get(new_asset_id)
            if h is None:
                return None, f"Holding {new_asset_id!r} not found."
            new_ticker = h.ticker
        else:
            new_ticker = ""

    # Reverse old cash effects (negating reversal entry — audit trail intact)
    if orig.account_id:
        from portfolio.accounts import load_accounts as _la, update_account_cash as _uac
        from portfolio.cash_ledger import append_cash_entry as _ace
        if orig.account_id in _la():
            _ace(
                account_id=orig.account_id,
                transaction_type=_SETTLE_LEDGER_TYPE.get(orig.settlement_category, "OTHER"),
                currency=orig.settlement_currency,
                amount=-orig.settlement_amount,
                linked_ticker=orig.ticker,
                notes=f"[Reversal of {orig.transaction_id}] {orig.notes[:60]}",
            )
            _uac(orig.account_id, -orig.settlement_amount)

    # Update transaction record
    orig.settlement_amount   = new_amount
    orig.settlement_category = new_category
    orig.settlement_currency = new_currency
    orig.date                = new_date
    orig.notes               = new_notes
    orig.asset_id            = new_asset_id
    orig.ticker              = new_ticker
    orig.account_id          = new_acct_id
    txns[idx] = orig
    save_transactions(txns)

    # Post new cash effects
    if new_acct_id:
        from portfolio.accounts import load_accounts as _la, update_account_cash as _uac
        from portfolio.cash_ledger import append_cash_entry as _ace
        if new_acct_id in _la():
            _ace(
                account_id=new_acct_id,
                transaction_type=_SETTLE_LEDGER_TYPE.get(new_category, "OTHER"),
                currency=new_currency,
                amount=new_amount,
                linked_ticker=new_ticker,
                notes=new_notes,
            )
            _uac(new_acct_id, new_amount)

    return orig, None


def delete_settlement(transaction_id: str) -> "str | None":
    """
    Delete a settlement and reverse its cash effects via a negating
    cash-ledger entry (audit trail preserved).

    Returns None on success, error string on failure.
    """
    txns = load_transactions()
    idx = next(
        (i for i, t in enumerate(txns) if t.transaction_id == transaction_id),
        None,
    )
    if idx is None:
        return f"Transaction {transaction_id!r} not found."
    orig = txns[idx]
    if orig.side != "SETTLEMENT":
        return f"Transaction {transaction_id!r} is not a SETTLEMENT."

    # Reverse cash effects
    if orig.account_id:
        from portfolio.accounts import load_accounts as _la, update_account_cash as _uac
        from portfolio.cash_ledger import append_cash_entry as _ace
        if orig.account_id in _la():
            _ace(
                account_id=orig.account_id,
                transaction_type=_SETTLE_LEDGER_TYPE.get(orig.settlement_category, "OTHER"),
                currency=orig.settlement_currency,
                amount=-orig.settlement_amount,
                linked_ticker=orig.ticker,
                notes=f"[Deleted {orig.transaction_id}] {orig.notes[:60]}",
            )
            _uac(orig.account_id, -orig.settlement_amount)

    txns.pop(idx)
    save_transactions(txns)
    return None

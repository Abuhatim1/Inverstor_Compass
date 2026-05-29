"""
portfolio/closed_holdings.py
-----------------------------
Closed Holdings — positions fully or partially sold, tracked with FIFO realized P&L.

Design:
  · Every SELL creates one or more ClosedLot records (FIFO matching).
  · ClosedLot records are immutable once written.
  · load_closed_holdings() aggregates lots into per-ticker ClosedHolding summaries.
  · Undo (reopen) soft-deletes lots via voided=True.

Storage:
  · edgar_app/portfolio/closed_lots.json  — list[ClosedLot]  (append-only)
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime


_DIR              = os.path.dirname(__file__)
_CLOSED_LOTS_FILE = os.path.join(_DIR, "closed_lots.json")


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class ClosedLot:
    """One FIFO lot matched against a SELL transaction."""
    lot_id:           str   = field(default_factory=lambda: str(uuid.uuid4())[:12])
    ticker:           str   = ""
    company_name:     str   = ""
    currency:         str   = "USD"
    quantity:         float = 0.0
    buy_price:        float = 0.0
    sell_price:       float = 0.0
    buy_value:        float = 0.0
    sell_value:       float = 0.0
    sell_fees:        float = 0.0
    realized_pnl:     float = 0.0
    realized_pnl_pct: float = 0.0
    open_date:        str   = ""
    close_date:       str   = ""
    sell_txn_id:      str   = ""
    account_id:       str   = ""
    notes:            str   = ""
    recorded_at:      str   = field(default_factory=lambda: datetime.now().isoformat())
    voided:           bool  = False
    voided_at:        str   = ""
    void_reason:      str   = ""

    @property
    def holding_period_days(self) -> int:
        try:
            return max(0, (date.fromisoformat(self.close_date) - date.fromisoformat(self.open_date)).days)
        except (ValueError, TypeError):
            return 0

    @property
    def holding_period_label(self) -> str:
        d = self.holding_period_days
        if d < 30:
            return f"{d}d"
        if d < 365:
            return f"{d // 30}mo"
        return f"{d / 365:.1f}yr"


@dataclass
class ClosedHolding:
    """Aggregated summary of all non-voided closed lots for one ticker."""
    ticker:               str
    company_name:         str
    currency:             str
    total_quantity:       float
    avg_buy_price:        float
    avg_sell_price:       float
    total_buy_value:      float
    total_sell_value:     float
    total_fees:           float
    realized_pnl:         float
    realized_pnl_pct:     float
    first_open_date:      str
    last_close_date:      str
    holding_period_label: str
    lots:                 list[ClosedLot]


@dataclass
class RealizedSummary:
    total_realized_pnl: float
    total_buy_value:    float
    total_sell_value:   float
    total_fees:         float
    n_closed:           int
    n_winners:          int
    n_losers:           int
    win_rate_pct:       float
    avg_return_pct:     float


# ── Persistence ────────────────────────────────────────────────────────────────

def _load_lots_raw() -> list[dict]:
    if not os.path.exists(_CLOSED_LOTS_FILE):
        return []
    try:
        with open(_CLOSED_LOTS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_lots_raw(lots: list[dict]) -> None:
    os.makedirs(_DIR, exist_ok=True)
    with open(_CLOSED_LOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(lots, f, indent=2, ensure_ascii=False)


def load_closed_lots() -> list[ClosedLot]:
    import dataclasses
    valid = {f.name for f in dataclasses.fields(ClosedLot)}
    out = []
    for entry in _load_lots_raw():
        if not isinstance(entry, dict):
            continue
        try:
            out.append(ClosedLot(**{k: v for k, v in entry.items() if k in valid}))
        except Exception:
            continue
    return out


def save_closed_lots(lots: list[ClosedLot]) -> None:
    _save_lots_raw([asdict(lot) for lot in lots])


def append_closed_lots(new_lots: list[ClosedLot]) -> None:
    raw = _load_lots_raw()
    raw.extend(asdict(lot) for lot in new_lots)
    _save_lots_raw(raw)


# ── Query helpers ──────────────────────────────────────────────────────────────

def load_closed_holdings() -> dict[str, ClosedHolding]:
    """Aggregate non-voided lots into per-ticker ClosedHolding summaries."""
    lots = [l for l in load_closed_lots() if not l.voided]
    if not lots:
        return {}

    groups: dict[str, list[ClosedLot]] = {}
    for lot in lots:
        groups.setdefault(lot.ticker, []).append(lot)

    out: dict[str, ClosedHolding] = {}
    for ticker, ticker_lots in sorted(groups.items()):
        total_qty    = sum(l.quantity    for l in ticker_lots)
        total_buy_v  = sum(l.buy_value   for l in ticker_lots)
        total_sell_v = sum(l.sell_value  for l in ticker_lots)
        total_fees   = sum(l.sell_fees   for l in ticker_lots)
        realized     = round(total_sell_v - total_buy_v - total_fees, 4)
        pnl_pct      = round(realized / total_buy_v * 100.0, 2) if total_buy_v > 0 else 0.0
        avg_buy      = round(total_buy_v  / total_qty, 4) if total_qty > 0 else 0.0
        avg_sell     = round(total_sell_v / total_qty, 4) if total_qty > 0 else 0.0

        open_dates  = [l.open_date  for l in ticker_lots if l.open_date]
        close_dates = [l.close_date for l in ticker_lots if l.close_date]
        first_open  = min(open_dates)  if open_dates  else ""
        last_close  = max(close_dates) if close_dates else ""

        try:
            hp_days = max(0, (date.fromisoformat(last_close) - date.fromisoformat(first_open)).days)
            if hp_days < 30:
                hp_label = f"{hp_days}d"
            elif hp_days < 365:
                hp_label = f"{hp_days // 30}mo"
            else:
                hp_label = f"{hp_days / 365:.1f}yr"
        except (ValueError, TypeError):
            hp_label = "—"

        out[ticker] = ClosedHolding(
            ticker               = ticker,
            company_name         = ticker_lots[-1].company_name,
            currency             = ticker_lots[-1].currency,
            total_quantity       = round(total_qty,   4),
            avg_buy_price        = avg_buy,
            avg_sell_price       = avg_sell,
            total_buy_value      = round(total_buy_v,  4),
            total_sell_value     = round(total_sell_v, 4),
            total_fees           = round(total_fees,   4),
            realized_pnl         = realized,
            realized_pnl_pct     = pnl_pct,
            first_open_date      = first_open,
            last_close_date      = last_close,
            holding_period_label = hp_label,
            lots                 = ticker_lots,
        )
    return out


def void_lots_for_ticker(ticker: str, void_reason: str = "Reopened") -> int:
    """Soft-delete all non-voided lots for a ticker. Returns count voided."""
    lots = load_closed_lots()
    count = 0
    now = datetime.now().isoformat()
    for lot in lots:
        if lot.ticker == ticker and not lot.voided:
            lot.voided      = True
            lot.voided_at   = now
            lot.void_reason = void_reason
            count += 1
    if count:
        save_closed_lots(lots)
    return count


def compute_realized_summary(closed: dict[str, ClosedHolding] | None = None) -> RealizedSummary:
    if closed is None:
        closed = load_closed_holdings()
    if not closed:
        return RealizedSummary(0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0.0, 0.0)
    n       = len(closed)
    winners = sum(1 for c in closed.values() if c.realized_pnl > 0)
    losers  = sum(1 for c in closed.values() if c.realized_pnl < 0)
    return RealizedSummary(
        total_realized_pnl = round(sum(c.realized_pnl     for c in closed.values()), 2),
        total_buy_value    = round(sum(c.total_buy_value  for c in closed.values()), 2),
        total_sell_value   = round(sum(c.total_sell_value for c in closed.values()), 2),
        total_fees         = round(sum(c.total_fees       for c in closed.values()), 2),
        n_closed           = n,
        n_winners          = winners,
        n_losers           = losers,
        win_rate_pct       = round(winners / n * 100.0, 1) if n > 0 else 0.0,
        avg_return_pct     = round(sum(c.realized_pnl_pct for c in closed.values()) / n, 2) if n > 0 else 0.0,
    )


# ── FIFO engine ────────────────────────────────────────────────────────────────

@dataclass
class _BuyLot:
    quantity:   float
    price:      float
    open_date:  str
    account_id: str = ""


def _build_fifo_queue(ticker: str) -> list[_BuyLot]:
    """Reconstruct remaining open buy lots by replaying transaction history (FIFO)."""
    from .holdings import load_transactions, normalize_ticker
    norm = normalize_ticker(ticker)
    txns = sorted(
        [t for t in load_transactions() if normalize_ticker(t.ticker) == norm],
        key=lambda t: (t.date, t.recorded_at),
    )
    queue: list[_BuyLot] = []
    for txn in txns:
        if txn.side == "BUY":
            queue.append(_BuyLot(float(txn.quantity), float(txn.price), txn.date, txn.account_id))
        elif txn.side == "SELL":
            remaining = float(txn.quantity)
            while remaining > 1e-9 and queue:
                lot = queue[0]
                if lot.quantity <= remaining + 1e-9:
                    remaining -= lot.quantity
                    queue.pop(0)
                else:
                    lot.quantity -= remaining
                    remaining = 0.0
    return queue


def execute_sell_fifo(
    ticker:             str,
    company_name:       str,
    currency:           str,
    quantity:           float,
    sell_price:         float,
    sell_date:          str,
    account_id:         str   = "",
    fees:               float = 0.0,
    notes:              str   = "",
    sell_txn_id:        str   = "",
    # Fallback for holdings added via upsert (no BUY transaction history)
    fallback_avg_cost:  float = 0.0,
    fallback_open_date: str   = "",
) -> tuple[list[ClosedLot], str | None]:
    """
    Match *quantity* against the FIFO queue and return (lots, error).
    Does NOT write anything — caller persists after confirming holding update.

    If the FIFO queue (rebuilt from transaction history) has fewer shares than
    requested — e.g. the holding was added directly via upsert_holding() rather
    than through a BUY transaction — the gap is filled with a synthetic lot at
    *fallback_avg_cost* so the sell can always succeed as long as the holding
    record itself confirms sufficient shares exist.
    """
    if quantity <= 0:
        return [], "Sell quantity must be > 0."
    queue     = _build_fifo_queue(ticker)
    available = sum(l.quantity for l in queue)

    # Fill the gap with a synthetic fallback lot (holding avg cost)
    gap = quantity - available
    if gap > 1e-9 and fallback_avg_cost > 0:
        queue.append(_BuyLot(
            quantity=gap,
            price=fallback_avg_cost,
            open_date=fallback_open_date or sell_date,
        ))
        available += gap

    if available < quantity - 1e-9:
        return [], (
            f"Cannot sell {quantity:.4f} of {ticker}: "
            f"only {available:.4f} available in transaction history."
        )

    lots: list[ClosedLot] = []
    remaining = quantity
    for lot in queue:
        if remaining <= 1e-9:
            break
        matched    = min(lot.quantity, remaining)
        proportion = matched / quantity if quantity > 0 else 0.0
        lot_fees   = round(fees * proportion, 8)
        buy_val    = round(matched * lot.price,  8)
        sell_val   = round(matched * sell_price, 8)
        rpnl       = round(sell_val - buy_val - lot_fees, 8)
        rpnl_pct   = round(rpnl / buy_val * 100.0, 2) if buy_val > 0 else 0.0
        lots.append(ClosedLot(
            ticker=ticker, company_name=company_name, currency=currency,
            quantity=round(matched, 8), buy_price=round(lot.price, 8),
            sell_price=round(sell_price, 8), buy_value=buy_val,
            sell_value=sell_val, sell_fees=lot_fees,
            realized_pnl=rpnl, realized_pnl_pct=rpnl_pct,
            open_date=lot.open_date, close_date=sell_date,
            sell_txn_id=sell_txn_id, account_id=account_id, notes=notes,
        ))
        remaining -= matched
    return lots, None

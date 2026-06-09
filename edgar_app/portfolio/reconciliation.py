"""
portfolio/reconciliation.py
---------------------------
READ-ONLY data-integrity check: do stored holding quantities agree with what
the transaction history implies?

This DETECTS drift; it never repairs it (repair would touch a protected zone).

Per-asset rule:
    txn_qty = Σ(BUY.quantity − SELL.quantity)  matched by asset_id
    drift   = stored_quantity − txn_qty

Asymmetric severity (architect guidance), because openings only ever ADD shares
and "Record Existing Holding" (Mode A) legitimately has no BUY transaction:
    · no matching transactions   → "untracked"  (info)  — opening with no trade log
    · drift < −tol               → "error"      — stored qty is LOWER than trades imply
                                                   (a genuine discrepancy / lost trade)
    · drift > +tol               → "implied_opening" (info) — extra shares look like an
                                                   imported opening position; verify
    · |drift| ≤ tol              → "ok"
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DriftRecord:
    asset_id:   str
    ticker:     str
    stored_qty: float
    txn_qty:    float
    drift:      float
    severity:   str     # "ok" | "untracked" | "implied_opening" | "error"
    message:    str


@dataclass
class ReconciliationReport:
    records:   list                  # all non-ok DriftRecords
    n_ok:      int
    n_info:    int                   # untracked + implied_opening
    n_error:   int
    issues:    list = field(default_factory=list)   # error-severity records only

    @property
    def clean(self) -> bool:
        return self.n_error == 0


def reconcile_holdings(
    holdings:     dict,
    transactions: list,
    tol:          float = 1e-6,
) -> ReconciliationReport:
    """Compare stored holding quantities against transaction-implied quantities."""
    txn_qty: dict[str, float] = {}
    for t in transactions or []:
        side = getattr(t, "side", "")
        aid  = getattr(t, "asset_id", "")
        if not aid or side not in ("BUY", "SELL"):
            continue
        q = float(getattr(t, "quantity", 0.0))
        txn_qty[aid] = txn_qty.get(aid, 0.0) + (q if side == "BUY" else -q)

    records: list[DriftRecord] = []
    n_ok = n_info = n_error = 0

    for h in (holdings or {}).values():
        aid    = getattr(h, "asset_id", "")
        tkr    = getattr(h, "ticker", "")
        stored = float(getattr(h, "quantity", 0.0))
        has_txns = aid in txn_qty
        implied  = txn_qty.get(aid, 0.0)
        drift    = round(stored - implied, 8)

        if not has_txns:
            n_info += 1
            records.append(DriftRecord(
                aid, tkr, stored, 0.0, drift, "untracked",
                "No buy/sell transactions on record — opening position is untracked.",
            ))
        elif drift < -tol:
            n_error += 1
            records.append(DriftRecord(
                aid, tkr, stored, implied, drift, "error",
                f"Stored quantity ({stored:g}) is LOWER than transactions imply "
                f"({implied:g}). Possible lost trade or manual edit.",
            ))
        elif drift > tol:
            n_info += 1
            records.append(DriftRecord(
                aid, tkr, stored, implied, drift, "implied_opening",
                f"Stored quantity exceeds transactions by {drift:g} — looks like an "
                f"imported opening position. Verify it is intentional.",
            ))
        else:
            n_ok += 1

    issues = [r for r in records if r.severity == "error"]
    return ReconciliationReport(
        records = records,
        n_ok    = n_ok,
        n_info  = n_info,
        n_error = n_error,
        issues  = issues,
    )

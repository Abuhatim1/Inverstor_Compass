"""
portfolio/net_worth.py
----------------------
True Net Worth aggregation and monthly trend snapshots.

Net worth = holdings MV + cash accounts + alt investments (non-Closed)
            + crowdfunding accounts (Active)  — all FX-converted to base_ccy.

This module is UI-layer only — it reads from other engines but never modifies
their data.  It owns only networth_snapshots.json.

Snapshot rules
  · One snapshot per (calendar month, base_ccy) pair
  · Snapshot is recorded on the first render of a new month
  · Snapshots are append-only — historical entries are never overwritten
  · Format: [{"month": "YYYY-MM", "value": float, "ccy": "SAR"}, ...]
"""

from __future__ import annotations

import json
import os
from datetime import date

_BASE         = os.path.dirname(__file__)
_NW_SNAP_FILE = os.path.join(_BASE, "networth_snapshots.json")


def compute_extra_assets_base(
    igi_investments: dict,
    cf_accounts:     dict,
    base_ccy:        str,
    fx_rates:        dict,
) -> float:
    """
    Sum non-Closed alt-investment current_value + Active crowdfunding
    current_account_value, FX-converted to base_ccy.

    Parameters
    ----------
    igi_investments : dict[str, IGIInvestment]
    cf_accounts     : dict[str, CFAccount]
    base_ccy        : str
    fx_rates        : {ccy: FxRate}  — same dict produced by valuation engine

    Returns float rounded to 4 decimal places.
    """
    total = 0.0

    for inv in igi_investments.values():
        if inv.status == "Closed":
            continue
        rate_obj = fx_rates.get(inv.currency)
        rate = rate_obj.rate if rate_obj else 1.0
        total += inv.current_value * rate

    for acct in cf_accounts.values():
        if acct.status != "Active":
            continue
        rate_obj = fx_rates.get(acct.currency)
        rate = rate_obj.rate if rate_obj else 1.0
        total += acct.current_account_value * rate

    return round(total, 4)


def load_nw_snapshots(path: str | None = None) -> list[dict]:
    """Load the net-worth snapshot list from disk.  Returns [] if file absent."""
    p = path or _NW_SNAP_FILE
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save_nw_snapshots(snaps: list[dict], path: str | None = None) -> None:
    """Persist the snapshot list to disk."""
    p = path or _NW_SNAP_FILE
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(snaps, fh, indent=2)


def record_nw_snapshot_if_needed(
    net_worth: float,
    base_ccy:  str,
    path:      str | None = None,
) -> list[dict]:
    """
    Append one snapshot per calendar month.  Only the first render of a
    new month writes a snapshot — subsequent renders (including base-currency
    changes) do not overwrite or add a second snapshot for the same month.

    Returns the full snapshot list for immediate use by get_monthly_trend.
    """
    snaps      = load_nw_snapshots(path=path)
    this_month = date.today().strftime("%Y-%m")

    exists = any(s.get("month") == this_month for s in snaps)
    if not exists:
        snaps.append({"month": this_month, "value": net_worth, "ccy": base_ccy})
        save_nw_snapshots(snaps, path=path)

    return snaps


def get_monthly_trend(
    net_worth: float,
    base_ccy:  str,
    snaps:     list[dict],
) -> tuple[float | None, float | None]:
    """
    Compute (delta_abs, delta_pct) vs the month-start snapshot.

    Returns (None, None) when:
    - no snapshot exists for this calendar month, or
    - the snapshot was recorded in a different base currency (can't compare).
    """
    this_month  = date.today().strftime("%Y-%m")
    month_snaps = [s for s in snaps if s.get("month") == this_month]
    if not month_snaps:
        return None, None
    snap = month_snaps[0]
    if snap.get("ccy") != base_ccy:
        return None, None
    start_val = snap["value"]
    if start_val == 0:
        return None, None
    delta_abs = net_worth - start_val
    delta_pct = delta_abs / start_val * 100.0
    return round(delta_abs, 4), round(delta_pct, 2)

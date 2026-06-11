"""
portfolio/bs_snapshot.py
------------------------
Daily Balance Sheet snapshots for day-over-day change display.

Snapshot rules:
  · One snapshot per (calendar date, base_ccy) pair
  · Snapshot is written on the first render of a new day
  · List is append-only; capped at _MAX_ENTRIES to prevent unbounded growth
  · Read-only display layer — never mutates any other module's data

Format: [{"date": "YYYY-MM-DD", "ccy": "SAR", "port": float, "alts": float,
          "fixed": float, "assets": float, "debt": float, "net": float}, ...]
"""
from __future__ import annotations

import json
import os
from datetime import date

_BASE         = os.path.dirname(__file__)
_BS_SNAP_FILE = os.path.join(_BASE, "bs_daily_snapshots.json")
_MAX_ENTRIES  = 90      # ~3 months of daily entries; oldest are trimmed


# ── Persistence ───────────────────────────────────────────────────────────────

def load_bs_snapshots(path: str | None = None) -> list[dict]:
    """Load the Balance Sheet snapshot list.  Returns [] if file absent or corrupt."""
    p = path or _BS_SNAP_FILE
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_bs_snapshots(snaps: list[dict], path: str | None = None) -> None:
    """Persist the snapshot list (trimmed to _MAX_ENTRIES most recent entries)."""
    p = path or _BS_SNAP_FILE
    try:
        from portfolio._io import atomic_json_write
        atomic_json_write(p, snaps[-_MAX_ENTRIES:])
    except Exception:
        pass


# ── Public API ────────────────────────────────────────────────────────────────

def record_bs_snapshot_if_needed(
    components: dict,
    base_ccy:   str,
    path:       str | None = None,
) -> dict | None:
    """
    Write today's Balance Sheet snapshot if one does not yet exist for
    (today's date, base_ccy).  Call once per render — safe to call repeatedly.

    Parameters
    ----------
    components : dict — must contain keys: port, alts, fixed, assets, debt, net
    base_ccy   : str  — current base currency
    path       : str | None — override file path (for tests)

    Returns the most recent snapshot from a *previous* calendar day with
    matching ccy, or None when no prior-day snapshot exists.
    """
    today = date.today().isoformat()
    snaps = load_bs_snapshots(path=path)

    today_exists = any(
        s.get("date") == today and s.get("ccy") == base_ccy
        for s in snaps
    )
    if not today_exists:
        snap = {"date": today, "ccy": base_ccy}
        snap.update({
            k: round(float(v), 4)
            for k, v in components.items()
            if k in ("port", "alts", "fixed", "assets", "debt", "net")
        })
        snaps.append(snap)
        save_bs_snapshots(snaps, path=path)

    prev_snaps = [
        s for s in snaps
        if s.get("ccy") == base_ccy and s.get("date", "") < today
    ]
    if not prev_snaps:
        return None
    return max(prev_snaps, key=lambda s: s.get("date", ""))


def compute_bs_delta(
    current:   float,
    prev_snap: dict | None,
    key:       str,
) -> tuple[float | None, float | None]:
    """
    Compute (delta_abs, delta_pct) for one component vs the previous snapshot.

    Returns (None, None) when:
    - prev_snap is None, or
    - key absent in prev_snap, or
    - prev value is zero (division guard).
    """
    if prev_snap is None:
        return None, None
    pv = prev_snap.get(key)
    if pv is None:
        return None, None
    pv = float(pv)
    if pv == 0.0:
        return None, None
    d_abs = current - pv
    d_pct = d_abs / abs(pv) * 100.0
    return round(d_abs, 2), round(d_pct, 2)

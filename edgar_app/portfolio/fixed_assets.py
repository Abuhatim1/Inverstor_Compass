"""
portfolio/fixed_assets.py
--------------------------
Fixed Assets module.

Tracks illiquid, manually-valued assets outside the trading engines:
  · Real Estate (residential, commercial, land)
  · Vehicles
  · Precious Metals (physical gold/silver — not ETFs)
  · Business Stakes (private equity, unlisted companies)
  · Other (art, collectibles, etc.)

Net worth contribution: equity = max(0, current_value − outstanding_liability)
Sold assets are retained as history but excluded from net worth.

Storage
  fixed_assets.json   — dict keyed by asset_id

Rules
  · IDs are 8-char hex from uuid4, never reused
  · Sold assets are never deleted (kept as archive record)
  · equity = max(0, current_value − outstanding_liability)
  · outstanding_liability defaults to 0.0
  · purchase_price is optional (0.0 = unknown); unrealized gain shown only when > 0
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime

_BASE    = os.path.dirname(__file__)
_FA_FILE = os.path.join(_BASE, "fixed_assets.json")


# ── Constants ──────────────────────────────────────────────────────────────────

FIXED_ASSET_TYPES: list[str] = [
    "Real Estate",
    "Vehicle",
    "Precious Metals (Physical)",
    "Business Stake",
    "Other",
]

FA_STATUSES: list[str] = [
    "Active",
    "Sold",
]


# ── Utilities ──────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _ts() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ── Data class ─────────────────────────────────────────────────────────────────

@dataclass
class FixedAsset:
    asset_id:              str
    name:                  str
    asset_type:            str      # from FIXED_ASSET_TYPES
    currency:              str
    current_value:         float    # manually entered appraisal
    outstanding_liability: float    # mortgage / loan amount (0.0 if none)
    purchase_price:        float    # 0.0 = unknown / not entered
    purchase_date:         str      # ISO date string, "" if unknown
    status:                str      # "Active" | "Sold"
    notes:                 str = ""
    created_at:            str = ""
    updated_at:            str = ""

    @property
    def equity(self) -> float:
        """Net equity = max(0, current_value − outstanding_liability)."""
        return max(0.0, round(self.current_value - self.outstanding_liability, 6))

    @property
    def unrealized_gain(self) -> float | None:
        """current_value − purchase_price. None if purchase_price unknown (0)."""
        if self.purchase_price <= 0:
            return None
        return round(self.current_value - self.purchase_price, 6)


# ── Persistence ────────────────────────────────────────────────────────────────

def _from_dict(d: dict) -> FixedAsset:
    return FixedAsset(
        asset_id              = d.get("asset_id", ""),
        name                  = d.get("name", ""),
        asset_type            = d.get("asset_type", "Other"),
        currency              = d.get("currency", "SAR"),
        current_value         = float(d.get("current_value", 0.0)),
        outstanding_liability = float(d.get("outstanding_liability", 0.0)),
        purchase_price        = float(d.get("purchase_price", 0.0)),
        purchase_date         = d.get("purchase_date", ""),
        status                = d.get("status", "Active"),
        notes                 = d.get("notes", ""),
        created_at            = d.get("created_at", ""),
        updated_at            = d.get("updated_at", ""),
    )


def load_fixed_assets(path: str | None = None) -> dict[str, FixedAsset]:
    """Load fixed assets from disk.  Returns {} if file absent."""
    p = path or _FA_FILE
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {k: _from_dict(v) for k, v in raw.items()}


def save_fixed_assets(assets: dict[str, FixedAsset], path: str | None = None) -> None:
    p = path or _FA_FILE
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({k: asdict(v) for k, v in assets.items()}, fh, indent=2)


# ── Business logic ─────────────────────────────────────────────────────────────

def add_fixed_asset(
    name:                  str,
    asset_type:            str,
    currency:              str,
    current_value:         float,
    outstanding_liability: float     = 0.0,
    purchase_price:        float     = 0.0,
    purchase_date:         str       = "",
    notes:                 str       = "",
    path:                  str | None = None,
) -> tuple[FixedAsset | None, str | None]:
    """Create and persist a new fixed asset.  Returns (asset, None) on success."""
    if not name.strip():
        return None, "Asset name is required."
    if asset_type not in FIXED_ASSET_TYPES:
        return None, f"Invalid asset type: {asset_type!r}."
    if current_value < 0:
        return None, "Current value cannot be negative."
    if outstanding_liability < 0:
        return None, "Outstanding liability cannot be negative."
    if purchase_price < 0:
        return None, "Purchase price cannot be negative."

    asset_id = _new_id()
    now      = _ts()
    asset    = FixedAsset(
        asset_id              = asset_id,
        name                  = name.strip(),
        asset_type            = asset_type,
        currency              = currency,
        current_value         = round(current_value, 6),
        outstanding_liability = round(outstanding_liability, 6),
        purchase_price        = round(purchase_price, 6),
        purchase_date         = purchase_date,
        status                = "Active",
        notes                 = notes.strip(),
        created_at            = now,
        updated_at            = now,
    )
    assets = load_fixed_assets(path=path)
    assets[asset_id] = asset
    save_fixed_assets(assets, path=path)
    return asset, None


def edit_fixed_asset(
    asset_id: str,
    path:     str | None = None,
    **kwargs,
) -> tuple[FixedAsset | None, str | None]:
    """
    Edit fields of an Active fixed asset.
    Editable: name, asset_type, currency, current_value,
              outstanding_liability, purchase_price, purchase_date, notes.
    """
    assets = load_fixed_assets(path=path)
    if asset_id not in assets:
        return None, f"Asset {asset_id!r} not found."
    asset = assets[asset_id]
    if asset.status == "Sold":
        return None, "Sold assets cannot be edited."

    editable = {
        "name", "asset_type", "currency", "current_value",
        "outstanding_liability", "purchase_price", "purchase_date", "notes",
    }
    for k, v in kwargs.items():
        if k in editable:
            setattr(asset, k, v)
    asset.updated_at = _ts()
    assets[asset_id] = asset
    save_fixed_assets(assets, path=path)
    return asset, None


def sell_fixed_asset(
    asset_id: str,
    path:     str | None = None,
) -> tuple[bool, str | None]:
    """
    Mark an asset as Sold.
    Sold assets are excluded from net worth but remain in history.
    """
    assets = load_fixed_assets(path=path)
    if asset_id not in assets:
        return False, f"Asset {asset_id!r} not found."
    asset = assets[asset_id]
    if asset.status == "Sold":
        return False, "Asset is already marked as Sold."
    asset.status     = "Sold"
    asset.updated_at = _ts()
    assets[asset_id] = asset
    save_fixed_assets(assets, path=path)
    return True, None


def compute_fixed_assets_equity(
    assets:   dict[str, FixedAsset],
    base_ccy: str,
    fx_rates: dict,
) -> float:
    """
    Sum equity for all non-Sold assets, FX-converted to base_ccy.

    Parameters
    ----------
    assets   : dict[str, FixedAsset]
    base_ccy : str
    fx_rates : {ccy: FxRate}  — same dict produced by valuation engine

    Returns float rounded to 4 decimal places.
    """
    total = 0.0
    for asset in assets.values():
        if asset.status == "Sold":
            continue
        rate_obj = fx_rates.get(asset.currency)
        rate     = rate_obj.rate if rate_obj else 1.0
        total   += asset.equity * rate
    return round(total, 4)

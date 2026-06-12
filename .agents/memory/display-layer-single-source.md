---
name: Display-layer single source of truth
description: >
  Rule and pattern for preventing KPI mismatch across tabs: any metric shown in
  ≥2 places must be computed by ONE shared function with identical inputs, using
  ONE shared formatter. Learned from the Holdings/Allocation ↔ Balance Sheet
  divergence (Task #64).
---

## The Rule

> **If the same monetary metric appears in ≥2 render locations, exactly ONE
> shared function must compute it, and exactly ONE shared formatter must render
> it. Consumers call the function with identical inputs; they never re-derive the
> value independently.**

## Why

Dual independent computations silently diverge when:
1. They pull from different intermediate variables (e.g. per-holding rows vs
   raw holdings dict), even when both should equal the same engine total.
2. They apply different formatters — two formatters on the same float can produce
   "123.5K" vs "123,457" (looks like a mismatch to the user even when the float
   is bit-identical).
3. Day-change % uses different denominators (% of current vs % of previous).

All three were present in the Holdings/Allocation vs Balance Sheet bug.

## How to Apply

**Before building a new KPI:**
- `grep` for the underlying field name (`holdings_value_base`, `daily_change_pct`,
  `base_market_value`, etc.) across all `render_*` functions and tab bodies.
- If the field is already rendered elsewhere, **reuse the computed variable** —
  do not recompute it.

**When two render locations need the same computed value:**
- Add a pure function to `edgar_app/portfolio/display_metrics.py` (no `st.*`,
  no file I/O, takes data as arguments so `dev_test_runner` can exercise it).
- Both consumers `import` and call it with the **same source object** (e.g.
  `val.per_holding` from the engine, not re-derived quantities).
- Both consumers apply `fmt_money_compact` from `display_metrics` for the
  rendered string — never two different formatters on the same value.

**Formatter rule:**
- `fmt_money_compact(v)` is the canonical compact formatter for monetary KPIs.
- `_fmt_compact` in `app.py` delegates to it (behavior-preserving, single source
  of truth).
- `_bs_fmt` in the Balance Sheet render delegates to it.
- Do NOT add a new money formatter anywhere. Extend `fmt_money_compact` if
  needed.

## Pattern: shared helper

```python
# edgar_app/portfolio/display_metrics.py
def compute_portfolio_day_change(per_holding, session, normalize_fn=None):
    """Returns (port_value, day_abs, day_pct, live_cnt) — %-of-previous."""
    ...

def fmt_money_compact(v):
    """Canonical: ≥1M → '1.23M', ≥10K → '12.3K', else '1,234.56'."""
    ...
```

```python
# In app.py (both Allocation and Balance Sheet tabs):
from portfolio.display_metrics import compute_portfolio_day_change, fmt_money_compact
pv, da, dp, cnt = compute_portfolio_day_change(val.per_holding, session, normalize)
# Render: fmt_money_compact(pv), fmt_money_compact(da), f"{dp:.1f}%"
```

## Cross-tab consistency test

The `_cat_consist()` test category in `dev_test_runner.py` exercises the shared
helper with synthetic data and verifies:
- `port_value == holdings_value_base` (reconciliation invariant).
- day-Δ math (%-of-previous formula).
- `.SE → .SR` ticker normalization.
- missing-FX holdings counted at rate 1.0 (matches BS).
- empty session → `None` guards fire.

**Never remove or reduce this category** — it is the regression guard for the
dual-tab consistency contract.

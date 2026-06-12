---
name: Display-layer single source of truth
description: >
  Architectural rule for preventing KPI mismatch across tabs: one shared function,
  one shared formatter, identical inputs. Includes the day-change overlay convention.
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

All three were present in the Holdings/Allocation vs Balance Sheet KPI mismatch.

## How to Apply

**Before building a new KPI:** `grep` for the underlying engine field across all
render functions. If it is already rendered elsewhere, **reuse the computed
variable** — do not recompute it.

**When two locations need the same value:** Add a pure function to
`edgar_app/portfolio/display_metrics.py` (no Streamlit, no file I/O, takes data
as arguments so `dev_test_runner` can exercise it with synthetic data).

**Formatter:** Use the canonical compact formatter in `display_metrics` for all
monetary KPIs. Do not add a second formatter; extend the existing one if needed.

## Day-change overlay convention

The established convention for the daily-change sub-line is:

    day_abs_i = mv_i × pct_i / (100 + pct_i)   # "%-of-current" formula

where `mv_i` is today's stored `base_market_value` (the value after the last
price refresh), and the implied-previous value is `mv - day_abs`. The **headline
KPI value remains the stored MV** — the overlay only affects the sub-line delta,
not the headline figure itself.

**Why this formula:** Treats `base_market_value` as today's live price (correct
after refresh) and back-computes yesterday's value. Using `mv × pct/100` instead
would assume `mv` is yesterday's price and risk double-counting after a refresh
bundle is already updated.

**How to apply:** Any new day-Δ computation must use this formula and derive
`day_pct = day_abs / (mv - day_abs) × 100`. Never use two different denominators
for the same conceptual delta across tabs.

## Regression guard

The `_cat_consist()` test category in `dev_test_runner.py` exercises the shared
display-layer helpers with synthetic in-memory data and verifies:
- Portfolio total == `holdings_value_base` (reconciliation invariant).
- Day-Δ math uses the correct `pct/(100+pct)` formula.
- `.SE → .SR` ticker normalization works.
- Empty-session guards return `None` for optional fields.
- Holdings map total == aggregate total (three-way equality invariant).
- BS identity: `port + cash + alts + fixed == total_assets`; `total_assets - debt == net`.

**Never remove or reduce this category** — it is the regression guard for the
dual-tab consistency contract.

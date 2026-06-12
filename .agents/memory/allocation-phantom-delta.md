---
name: Allocation tab phantom daily Δ
description: Root cause and correct fix for the phantom daily change in the Allocation tab KPI.
---

## Rule
Never compare the Allocation tab's `_fas_mv` (filtered MV) against the BS snapshot's `port` key (total unfiltered portfolio). The mismatch produces a phantom delta proportional to the excluded portion.

**How to apply:** The Allocation tab daily Δ must use the session-cache weighted sum (`_day_from_session(_filt)`) only. If the session cache is empty (no 🔄 refresh), show "—". Do not add any snapshot fallback.

**Why:** `_fas_mv` is scoped to the current account / asset-type / sector filter. The BS snapshot `port` is the unfiltered total portfolio (all accounts, all asset types). Even with "All" selected, cash/alts/fixed are excluded from `_fas_mv` but included in `port`. Any fallback that subtracts the snapshot `port` from `_fas_mv` gives nonsense.

**Contrast:** The BS tab's snapshot comparison is correct because both the current value (`_bs_port`) and the snapshot value (`_bs_prev["port"]`) are computed by the same total unfiltered valuation engine.

## BS snapshot timing rule
`record_bs_snapshot_if_needed` always overwrites today's entry (not write-once). This ensures the snapshot always reflects the most recently seen prices (including post-refresh), so tomorrow's startup delta compares post-refresh prices against yesterday's post-refresh prices = actual market movement rather than a phantom from stale-snapshot vs fresh-stored-price mismatch.

## BS totals recompute gate
The `_bs_live_cnt > 0 and _bs_d_port_abs is not None` guard ensures Total Assets / Net Worth are re-derived from component deltas ONLY when live enrichment has actually fired. Snapshot-only startup deltas each have their own independent snapshot value and do not need recomputation.

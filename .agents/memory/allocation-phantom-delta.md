---
name: Allocation tab phantom daily Δ
description: Root cause and correct fix for the phantom −20% daily change in the Allocation tab KPI.
---

## Rule
Never compare the Allocation tab's `_fas_mv` (filtered MV) against the BS snapshot's `port` key (total unfiltered portfolio). The mismatch produces a phantom delta proportional to the excluded portion.

**How to apply:** The Allocation tab daily Δ must use the session-cache weighted sum (`_day_from_session(_filt)`) only. If the session cache is empty (no 🔄 refresh), show "—". Do not add any snapshot fallback.

**Why:** `_fas_mv` is scoped to the current account / asset-type / sector filter. The BS snapshot `port` is the unfiltered total portfolio (all accounts, all asset types). Even with "All" selected, cash/alts/fixed are excluded from `_fas_mv` but included in `port`. Any fallback that subtracts `_fbs_prev_port` from `_fas_mv` gives nonsense.

**Contrast:** The BS tab's snapshot comparison is correct because both the current value (`_bs_port`) and the snapshot value (`_bs_prev["port"]`) are computed by the same total unfiltered valuation engine.

## History
- Task #57: removed snapshot comparison from Allocation tab entirely (correct fix, wrong justification — blamed provider switching, not filter mismatch).
- Task #60: restored snapshot as "Priority 2 fallback" — reintroduced the bug.
- Task #61: removed snapshot fallback from Allocation tab again, documented filter-mismatch root cause.

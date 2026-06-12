"""
Display-layer portfolio metrics — READ-ONLY.

This module exists so the Holdings/Allocation "Market Value" KPI and the
Balance Sheet "Investment Portfolio" KPI render the *same* headline value and
the *same* daily-change overlay. It performs NO accounting: it only reads the
valuation engine's per-holding output plus an in-memory price session cache and
aggregates them for display. It never touches holdings, transactions, cash, FX,
FIFO, or the valuation engine itself.

It is intentionally pure and dependency-free (only the stdlib) so the developer
test runner can exercise it with synthetic in-memory data and no file I/O.

NOTE: this lives in its own module (not app.py) on purpose — app.py runs
``st.set_page_config`` at import time and therefore cannot be imported by tests.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional


def _norm_se_to_sr(ticker: str) -> str:
    """Fallback ticker normalizer: the Saudi Exchange ``.SE`` suffix is invalid
    for the price feed, so map it to ``.SR``. Kept as a tiny standalone copy so
    this module never has to import app.py's ``_normalize_ticker``."""
    t = (ticker or "").strip()
    if t.upper().endswith(".SE"):
        return t[:-3] + ".SR"
    return t


def fmt_money_compact(v: float) -> str:
    """Canonical compact money label shared by the Holdings/Allocation and
    Balance Sheet KPIs, so an identical value always renders as an identical
    string on both tabs.

        >>> fmt_money_compact(1_234_567.8)   # '1.23M'
        >>> fmt_money_compact(123_456.0)     # '123.5K'
        >>> fmt_money_compact(5_000.0)       # '5,000.00'
    """
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return str(v)
    av = abs(fv)
    if av >= 1_000_000:
        return f"{fv / 1_000_000:.2f}M"
    if av >= 10_000:
        return f"{fv / 1_000:.1f}K"
    return f"{fv:,.2f}"


def compute_portfolio_day_change(
    per_holding: Iterable,
    session: Optional[dict],
    normalize_fn: Optional[Callable[[str], str]] = None,
) -> tuple[float, Optional[float], Optional[float], int]:
    """Aggregate the investment-portfolio headline value and its live daily
    change overlay — identically for the Allocation summary and the Balance
    Sheet tab.

    Parameters
    ----------
    per_holding
        Iterable of ``PerHoldingValuation`` rows. Each row only needs ``.ticker``
        and ``.base_market_value``. Summing ``base_market_value`` reproduces the
        engine's ``holdings_value_base`` (engine-guaranteed reconciliation), so
        this helper never recomputes ``qty x price x fx`` independently and can
        never drift from the engine total.
    session
        In-memory price cache: ``dict`` keyed by normalized+upper ticker, whose
        values expose ``.daily_change_pct`` (``None`` when unavailable). Pass an
        empty dict / ``None`` before any price refresh.
    normalize_fn
        Optional ticker normalizer (defaults to ``.SE`` -> ``.SR``).

    Returns
    -------
    ``(port_value, day_abs, day_pct, live_cnt)``
        * ``port_value`` — sum of ``base_market_value`` over ALL rows
          (== ``holdings_value_base``).
        * ``day_abs`` — sum of ``mv * pct / (100 + pct)`` over the rows that have
          a live ``daily_change_pct``; ``None`` when no row has one.
        * ``day_pct`` — ``day_abs / (port_value - day_abs) * 100``, i.e. the
          change as a percentage of the *previous* (yesterday) value; ``None``
          when there is no live pct or the implied previous value is <= 0.
        * ``live_cnt`` — number of rows that contributed a live pct.
    """
    norm = normalize_fn or _norm_se_to_sr
    sess = session or {}
    port_value = 0.0
    day_abs = 0.0
    live_cnt = 0

    for row in per_holding:
        try:
            mv = float(getattr(row, "base_market_value", 0.0) or 0.0)
        except (TypeError, ValueError):
            mv = 0.0
        port_value += mv

        if not sess:
            continue
        tk = str(getattr(row, "ticker", "") or "").strip()
        if not tk:
            continue
        key = norm(tk).upper()
        md = sess.get(key) or sess.get(tk.upper()) or sess.get(tk)
        if md is None:
            continue
        pct = getattr(md, "daily_change_pct", None)
        if pct is None:
            continue
        denom = 100.0 + pct
        if denom == 0:
            continue
        day_abs += mv * pct / denom
        live_cnt += 1

    if live_cnt == 0:
        return port_value, None, None, 0

    prev = port_value - day_abs
    day_pct = (day_abs / prev * 100.0) if prev > 0 else None
    return (
        port_value,
        round(day_abs, 2),
        round(day_pct, 2) if day_pct is not None else None,
        live_cnt,
    )


def compute_effective_portfolio_mv(
    per_holding: Iterable,
    session: Optional[dict],
    normalize_fn: Optional[Callable[[str], str]] = None,
) -> tuple[float, float, Optional[float], Optional[float], int]:
    """Portfolio headline MV and daily-change overlay — the 5-tuple form of
    :func:`compute_portfolio_day_change` for callers that need both the headline
    value and the stored baseline in one call.

    Uses the same ``mv × pct / (100 + pct)`` convention as
    :func:`compute_portfolio_day_change` so the two helpers are always
    consistent.  The *headline* (``effective_total``) is the sum of stored
    ``base_market_value`` from the engine — the overlay only affects
    ``day_abs``/``day_pct`` (the sub-line), not the KPI headline itself.

    Parameters
    ----------
    per_holding
        Iterable of ``PerHoldingValuation`` rows (needs ``.ticker`` and
        ``.base_market_value``).
    session
        In-memory price cache keyed by normalised+upper ticker; values expose
        ``.daily_change_pct``.  Pass ``{}`` / ``None`` before any refresh.
    normalize_fn
        Optional ticker normalizer (defaults to ``.SE`` → ``.SR``).

    Returns
    -------
    ``(effective_total, stored_total, day_abs, day_pct, live_cnt)``

    * ``effective_total`` — headline value = ``sum(base_market_value)``
      (== ``holdings_value_base``; unchanged by session overlay).
    * ``stored_total``   — same as ``effective_total`` (exposed separately so
      callers can assert the two are equal as a consistency invariant).
    * ``day_abs``        — ``Σ mv × pct / (100 + pct)`` over live-pct rows;
      ``None`` when ``live_cnt == 0``.
    * ``day_pct``        — ``day_abs / (port_value − day_abs) × 100`` (change
      as % of the implied-previous value); ``None`` when no live pct or the
      implied previous ≤ 0.
    * ``live_cnt``       — number of rows that contributed a live pct.
    """
    rows = list(per_holding)  # consume once so we can inspect length
    port_value, day_abs, day_pct, live_cnt = compute_portfolio_day_change(
        rows, session, normalize_fn
    )
    return port_value, port_value, day_abs, day_pct, live_cnt


def build_effective_mv_map(
    per_holding: Iterable,
    session: Optional[dict] = None,
    normalize_fn: Optional[Callable[[str], str]] = None,
) -> dict:
    """Return ``{asset_id: base_market_value}`` — the authoritative base-CCY MV
    per holding from the valuation engine.

    This is the base-currency form of the MV map used for Holdings table row
    display.  The "effective" label signals that this map is the single source
    of truth aligned with :func:`compute_effective_portfolio_mv`: the sum of
    all values in this dict equals ``effective_total`` (and ``holdings_value_base``)
    exactly, guaranteeing Holdings row total ≡ Allocation KPI ≡ BS headline
    by construction.

    ``session`` and ``normalize_fn`` are accepted for API symmetry with
    :func:`compute_effective_portfolio_mv` but are not used in the headline
    value calculation (the overlay is ``day_abs``-only per the
    ``pct / (100 + pct)`` convention).

    Falls back to an empty dict when ``per_holding`` is ``None``/empty.
    """
    return {
        getattr(r, "asset_id", ""): float(getattr(r, "base_market_value", 0.0) or 0.0)
        for r in (per_holding or [])
    }


def build_effective_local_mv_map(
    per_holding: Iterable,
    session: Optional[dict] = None,
    normalize_fn: Optional[Callable[[str], str]] = None,
) -> dict:
    """Return ``{asset_id: local_market_value}`` — the native-CCY MV per
    holding from the valuation engine, for Holdings table **native-currency
    display mode**.

    Paired with :func:`build_effective_mv_map` so both base and native display
    modes share the engine's single source of truth.  As with the base-CCY
    variant, the headline value is the stored ``local_market_value``; session
    overlay is ``day_abs``-only.
    """
    return {
        getattr(r, "asset_id", ""): float(getattr(r, "local_market_value", 0.0) or 0.0)
        for r in (per_holding or [])
    }


def build_mv_map(per_holding: Iterable) -> dict:
    """Return ``{asset_id: base_market_value}`` from the valuation engine's
    per-holding rows.

    **Use this as the authoritative MV source for Holdings table row display**
    so that the sum of all displayed row values equals the Allocation tab's
    "Market Value" KPI and the Balance Sheet tab's "Investment Portfolio" KPI
    exactly. Both of those headlines are derived from the same
    ``val.per_holding.base_market_value`` data, so using this map in the
    Holdings table rows guarantees three-way equality by construction rather
    than by coincidence of independent re-computations.

    Falls back gracefully (empty dict) when ``per_holding`` is ``None`` or
    empty, which allows Holdings tab code to provide a safe fallback.
    """
    return {r.asset_id: r.base_market_value for r in (per_holding or [])}


def build_local_mv_map(per_holding: Iterable) -> dict:
    """Return ``{asset_id: local_market_value}`` from the valuation engine's
    per-holding rows.

    Use for Holdings table **native-currency display mode** (``_native_mode``),
    where row MV is shown in the holding's own CCY without FX conversion.
    Keeping this in the same module as :func:`build_mv_map` ensures both
    display modes share the engine's source of truth.
    """
    return {r.asset_id: r.local_market_value for r in (per_holding or [])}

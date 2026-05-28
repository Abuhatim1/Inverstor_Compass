"""
ai/evidence.py
--------------
Evidence Grounding Layer.

EvidenceItem attaches a source quote, filing section, extracted metric,
and confidence level to every AI conclusion about a financial field.

Six canonical fields are always requested:
  revenue_growth, margins, cash_position, debt, guidance, management_tone

Confidence levels
-----------------
  "high"   — specific number or verbatim quote found in the excerpt
  "medium" — implied or inferred from context
  "low"    — not mentioned; the AI conclusion is unsupported by the excerpt

When confidence is "low", the UI replaces the trend label with
"❓ Low confidence" so unsupported conclusions are never displayed
as facts.
"""

from dataclasses import dataclass

# ── Canonical evidence fields ─────────────────────────────────────────────────
EVIDENCE_FIELDS = [
    "revenue_growth",
    "margins",
    "cash_position",
    "debt",
    "guidance",
    "management_tone",
]

# Human-readable label for each field
FIELD_LABELS = {
    "revenue_growth":  "Revenue Growth",
    "margins":         "Margins",
    "cash_position":   "Cash Position",
    "debt":            "Debt / Leverage",
    "guidance":        "Guidance",
    "management_tone": "Management Tone",
}

# Confidence badge: (icon, colour word for CSS class / caption)
CONFIDENCE_BADGE = {
    "high":   ("🟢", "High confidence"),
    "medium": ("🟡", "Medium confidence"),
    "low":    ("🔴", "Low confidence — limited data in excerpt"),
}


# ── Data structure ────────────────────────────────────────────────────────────

@dataclass
class EvidenceItem:
    field:          str   # one of EVIDENCE_FIELDS
    section:        str   # filing section, e.g. "MD&A", "Risk Factors", "not_mentioned"
    current_value:  str   # e.g. "$94.9B, +5% YoY"   or "not mentioned"
    previous_value: str   # e.g. "$90.1B"             or "" when no comparison
    delta:          str   # e.g. "+$4.8B / +5.3%"     or "" when no comparison
    quote:          str   # verbatim excerpt from filing (≤ 150 chars); "" if not found
    interpretation: str   # 1-sentence AI take
    confidence:     str   # "high" | "medium" | "low"


# ── Parser ────────────────────────────────────────────────────────────────────

def evidence_from_list(raw: list) -> list[EvidenceItem]:
    """
    Convert the raw list of dicts from the AI JSON response into EvidenceItem objects.
    Skips malformed entries silently — callers always get a (possibly empty) list back.
    """
    items: list[EvidenceItem] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            items.append(EvidenceItem(
                field=entry.get("field", ""),
                section=entry.get("section", ""),
                current_value=entry.get("current_value", ""),
                previous_value=entry.get("previous_value", ""),
                delta=entry.get("delta", ""),
                quote=entry.get("quote", ""),
                interpretation=entry.get("interpretation", ""),
                confidence=entry.get("confidence", "low"),
            ))
        except Exception:
            continue
    return items


def evidence_by_field(items: list[EvidenceItem]) -> dict[str, EvidenceItem]:
    """Return a field→EvidenceItem lookup dict for quick access in the UI."""
    return {item.field: item for item in items}

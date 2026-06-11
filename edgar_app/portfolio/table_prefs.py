import json
from pathlib import Path

_PREFS_FILE = Path(__file__).parent / "table_prefs.json"

DENSITY_OPTIONS = ["Compact", "Normal", "Wide"]

_DEFAULTS: dict = {
    "holdings_density": "Normal",
    "allocation_density": "Normal",
}


def load_prefs() -> dict:
    try:
        data = json.loads(_PREFS_FILE.read_text())
        return {**_DEFAULTS, **data}
    except Exception:
        return dict(_DEFAULTS)


def save_prefs(prefs: dict) -> None:
    try:
        _PREFS_FILE.write_text(json.dumps(prefs, indent=2))
    except Exception:
        pass


def holdings_col_widths(density: str) -> dict:
    if density == "Compact":
        return {
            " ": "small",
            "Ticker": "small",
            "Qty": "small",
            "Wt %": "small",
            "P&L %": "small",
            "Day %": "small",
            "CCY": "small",
            "Src": "small",
        }
    elif density == "Wide":
        return {" ": "small", "Company": "medium", "Account": "medium"}
    else:
        return {" ": "small"}


def allocation_col_widths(density: str) -> dict:
    if density == "Compact":
        return {"Ticker": "small", "CCY": "small"}
    elif density == "Wide":
        return {"Company": "medium"}
    else:
        return {}

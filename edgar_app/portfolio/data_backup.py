"""
portfolio/data_backup.py
------------------------
Export / Import all portfolio data as a single JSON bundle.

Export: reads every data file next to this module and returns a dict
        {filename: parsed_json} — safe to call at any time (read-only).

Import: writes each key back to the corresponding file, then triggers
        a st.rerun() so Streamlit re-loads fresh state.

Only files in BACKUP_FILES are included.  Any key in the bundle that
is NOT in BACKUP_FILES is silently ignored on restore (forward-compat).
"""

import json
import os
from datetime import datetime, timezone

_DIR = os.path.dirname(__file__)

# Ordered list of filenames that form a complete portfolio snapshot.
# Add new files here as the schema grows.
BACKUP_FILES = [
    "accounts.json",
    "_asset_counter.json",
    "alt_cf_accounts.json",
    "alt_cf_snapshots.json",
    "alt_cf_transactions.json",
    "alt_igi_transactions.json",
    "alt_investments.json",
    "cash_ledger.json",
    "closed_lots.json",
    "core_theses.json",
    "deleted_holdings.json",
    "fixed_assets.json",
    "holdings.json",
    "liabilities.json",
    "networth_snapshots.json",
    "portfolio_state.json",
    "transactions.json",
]

_BUNDLE_VERSION = 1


def export_bundle() -> dict:
    """
    Return a dict ready to be JSON-serialised and offered as a download.
    Files that don't exist yet are skipped (not an error).
    """
    files: dict = {}
    for fname in BACKUP_FILES:
        path = os.path.join(_DIR, fname)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    files[fname] = json.load(fh)
            except Exception:
                pass  # corrupt / empty file — skip silently

    return {
        "version": _BUNDLE_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }


def export_bundle_bytes() -> tuple[bytes, str]:
    """
    Return (json_bytes, suggested_filename) for use with st.download_button.
    """
    bundle = export_bundle()
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"bousala_backup_{ts}.json"
    return json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8"), filename


def import_bundle(raw: bytes) -> tuple[bool, str]:
    """
    Parse *raw* bytes as a backup bundle and restore all recognised files.

    Returns (success: bool, message: str).
    On success the caller should call st.rerun().
    """
    try:
        bundle = json.loads(raw)
    except Exception as exc:
        return False, f"Invalid JSON: {exc}"

    if not isinstance(bundle, dict):
        return False, "Bundle must be a JSON object."

    files = bundle.get("files")
    if not isinstance(files, dict):
        return False, "Bundle missing 'files' key."

    restored = 0
    skipped = 0
    errors: list[str] = []

    for fname, data in files.items():
        if fname not in BACKUP_FILES:
            skipped += 1
            continue
        path = os.path.join(_DIR, fname)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            restored += 1
        except Exception as exc:
            errors.append(f"{fname}: {exc}")

    if errors:
        return False, "Errors during restore:\n" + "\n".join(errors)

    exported_at = bundle.get("exported_at", "unknown time")
    msg = (
        f"Restored {restored} file(s) from backup exported at {exported_at}."
        + (f" ({skipped} unrecognised file(s) skipped)" if skipped else "")
    )
    return True, msg

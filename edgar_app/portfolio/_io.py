"""
Shared I/O utilities for the portfolio package.
"""
import json
import os
import tempfile


def atomic_json_write(filepath: str, payload, *, indent: int = 2) -> None:
    """
    Write *payload* as JSON to *filepath* atomically.

    Writes to a sibling temp file first, then renames it over the target.
    The rename is an OS-level atomic operation — the real file is never
    partially written. If the process crashes mid-write the old file
    survives intact.
    """
    dir_ = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dir_, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tf:
            json.dump(payload, tf, indent=indent, ensure_ascii=False)
        os.replace(tmp_path, filepath)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

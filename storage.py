"""storage.py — JSON persistence layer for the Telegram Lunch Bot.

Keyed by chat_id (str). Each entry is a dict with:
  - name     (str, original casing preserved)
  - added_by (str)
  - added_at (str, ISO 8601 with +08:00 offset)
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

from config import DATA_FILE

logger = logging.getLogger(__name__)


def _read_all() -> dict[str, Any]:
    """Read the entire JSON file. Returns empty dict if file is missing."""
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def load(chat_id: int | str) -> list[dict]:
    """Return the restaurant list for *chat_id*, or [] if absent."""
    data = _read_all()
    return data.get(str(chat_id), [])


def save(chat_id: int | str, restaurants: list[dict]) -> None:
    """Persist *restaurants* for *chat_id* atomically (write-then-rename)."""
    data = _read_all()
    data[str(chat_id)] = restaurants

    dir_name = os.path.dirname(DATA_FILE) or "."
    os.makedirs(dir_name, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, DATA_FILE)
    except Exception:
        # Clean up the temp file if something went wrong before the rename.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

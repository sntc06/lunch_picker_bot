"""storage.py — JSON persistence layer for the Telegram Lunch Bot.

Two JSON files live in the data folder, both keyed by chat_id (str):

  - ``DATA_FILE`` — the restaurant list for each chat. Each entry is a dict:
      * name     (str, original casing preserved)
      * added_by (str)
      * added_at (str, ISO 8601 with +08:00 offset)
  - ``PREVIOUS_ROLL_FILE`` — the most recent roll result for each chat,
    stored as a lowercase name string. Keeping it in a separate file leaves
    the restaurant-list format untouched (no migration needed).

Both files are read with a shared ``_read_json`` helper and written with a
shared atomic ``_atomic_write`` helper (write to a temp file, then rename) so
a crash mid-write cannot corrupt the persisted data.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

from config import DATA_FILE, PREVIOUS_ROLL_FILE

logger = logging.getLogger(__name__)


def _read_json(path: str) -> dict[str, Any]:
    """Read and parse the JSON file at *path*.

    Returns an empty dict if the file does not exist.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _atomic_write(path: str, data: Any) -> None:
    """Write *data* as JSON to *path* atomically (write-then-rename).

    The data is first written to a temp file in the same directory and then
    ``os.replace``d into place, so readers never observe a partial file.
    """
    dir_name = os.path.dirname(path) or "."
    os.makedirs(dir_name, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up the temp file if something went wrong before the rename.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load(chat_id: int | str) -> list[dict]:
    """Return the restaurant list for *chat_id*, or [] if absent."""
    data = _read_json(DATA_FILE)
    return data.get(str(chat_id), [])


def save(chat_id: int | str, restaurants: list[dict]) -> None:
    """Persist *restaurants* for *chat_id* atomically (write-then-rename)."""
    data = _read_json(DATA_FILE)
    data[str(chat_id)] = restaurants
    _atomic_write(DATA_FILE, data)


def load_previous_roll(chat_id: int | str) -> str | None:
    """Return the most recent roll result for *chat_id*, or None.

    Returns None when ``PREVIOUS_ROLL_FILE`` is missing or when the chat has
    no recorded result (i.e. no roll has ever produced a result for it).
    """
    data = _read_json(PREVIOUS_ROLL_FILE)
    return data.get(str(chat_id))


def save_previous_roll(chat_id: int | str, name: str) -> None:
    """Persist *name* as the previous roll result for *chat_id* atomically.

    The name is stored lowercase (consistent with restaurant-name storage)
    so membership comparisons against the restaurant list are reliable.
    """
    data = _read_json(PREVIOUS_ROLL_FILE)
    data[str(chat_id)] = name.lower()
    _atomic_write(PREVIOUS_ROLL_FILE, data)

"""storage.py — JSON persistence layer for the Telegram Lunch Bot.

Two JSON files live in the data folder, both keyed by chat_id (str):

  - ``DATA_FILE`` — the restaurant list for each chat. Each entry is a dict:
      * name     (str, original casing preserved)
      * added_by (str)
      * added_at (str, ISO 8601 with +08:00 offset)
  - ``RECENT_ROLLS_FILE`` — the bounded ``Recent_Roll_History`` for each chat,
    stored as an ordered JSON array of lowercase result names (most recent
    last). Keeping it in a separate file leaves the restaurant-list format
    untouched (no migration needed).

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

from config import DATA_FILE, RECENT_ROLLS_FILE

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


def load_recent_rolls(chat_id: int | str) -> list[str]:
    """Return the ordered Recent_Roll_History for *chat_id* (most recent last).

    Returns an empty list when ``RECENT_ROLLS_FILE`` is missing, the chat has
    no recorded entry, or the stored value cannot be read/parsed — i.e. the
    chat is treated as having no recorded history (Req 3a.10, 3a.17). Any
    read/parse failure is logged.
    """
    try:
        with open(RECENT_ROLLS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        logger.error(
            "Failed to read recent-roll history from %s: %s",
            RECENT_ROLLS_FILE,
            exc,
        )
        return []

    if not isinstance(data, dict):
        logger.error(
            "Recent-roll history in %s is not a JSON object; "
            "treating history as empty.",
            RECENT_ROLLS_FILE,
        )
        return []

    history = data.get(str(chat_id))
    if history is None:
        return []
    if not isinstance(history, list) or not all(
        isinstance(name, str) for name in history
    ):
        logger.error(
            "Recent-roll history for chat %s in %s is not a list of strings; "
            "treating history as empty.",
            chat_id,
            RECENT_ROLLS_FILE,
        )
        return []
    return history


def save_recent_rolls(chat_id: int | str, history: list[str]) -> None:
    """Persist the ordered *history* for *chat_id* atomically (write-then-rename).

    History is keyed by ``chat_id`` in ``RECENT_ROLLS_FILE`` and uses the same
    atomic write helper as the restaurant list, so a crash mid-write cannot
    corrupt the persisted data. History is tracked independently per chat
    (Req 3a.14, 5.3).
    """
    data = _read_json(RECENT_ROLLS_FILE)
    data[str(chat_id)] = history
    _atomic_write(RECENT_ROLLS_FILE, data)


def append_recent_roll(
    chat_id: int | str, name: str, window: int
) -> list[str]:
    """Append *name* to the chat's history, trim, persist, and return it.

    The new result is stored lowercase (consistent with restaurant-name
    storage) for case-insensitive membership comparison. After appending, the
    history is trimmed to the most recent *window* entries (keeping the
    newest) and persisted (Req 3a.12).

    On persistence failure, the error is logged and the updated in-memory
    history is still returned so the caller can retain it for the run
    (Req 3a.16).
    """
    history = load_recent_rolls(chat_id)
    history.append(name.lower())

    # Trim to the most recent `window` entries (keeping the newest). A window
    # of 0 or less keeps no history.
    if window <= 0:
        history = []
    elif len(history) > window:
        history = history[-window:]

    try:
        save_recent_rolls(chat_id, history)
    except Exception as exc:
        logger.error(
            "Failed to persist recent-roll history for chat %s to %s: %s",
            chat_id,
            RECENT_ROLLS_FILE,
            exc,
        )

    return history

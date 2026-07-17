"""
Example (non-property) tests for graceful handling of a missing or corrupt
Recent_Roll_History file.

Validates: Requirements 3a.17

These assert that ``load_recent_rolls`` never raises and always degrades to an
empty history, logging a failure when the persisted data (whole file or a
per-chat entry) cannot be read/parsed.
"""
import importlib
import json
import logging
import os
import sys
import tempfile

import pytest


def _import_storage(mp, data_file: str, recent_file: str):
    """Import storage/config with RECENT_ROLLS_FILE pointed at *recent_file*."""
    # Drop cached modules so module-level config re-reads our temp paths.
    sys.modules.pop("storage", None)
    sys.modules.pop("config", None)

    mp.setenv("BOT_TOKEN", "test-token")
    mp.setenv("DATA_FILE", data_file)
    mp.setenv("RECENT_ROLLS_FILE", recent_file)

    importlib.import_module("config")
    return importlib.import_module("storage")


def test_returns_empty_when_file_missing():
    """A missing RECENT_ROLLS_FILE yields an empty history (no error)."""
    chat_id = 42

    with tempfile.TemporaryDirectory() as tmpdir:
        data_file = os.path.join(tmpdir, "restaurants.json")
        recent_file = os.path.join(tmpdir, "recent_rolls.json")

        with pytest.MonkeyPatch().context() as mp:
            storage = _import_storage(mp, data_file, recent_file)

            # The file was never created.
            assert not os.path.exists(recent_file)
            assert storage.load_recent_rolls(chat_id) == []

    sys.modules.pop("storage", None)
    sys.modules.pop("config", None)


def test_returns_empty_and_logs_when_whole_file_corrupt(caplog):
    """An unparseable RECENT_ROLLS_FILE yields [] and logs the failure."""
    chat_id = 42

    with tempfile.TemporaryDirectory() as tmpdir:
        data_file = os.path.join(tmpdir, "restaurants.json")
        recent_file = os.path.join(tmpdir, "recent_rolls.json")

        # Write invalid JSON so json.load raises ValueError.
        with open(recent_file, "w", encoding="utf-8") as f:
            f.write("{ this is not valid json ]]]")

        with pytest.MonkeyPatch().context() as mp:
            storage = _import_storage(mp, data_file, recent_file)

            with caplog.at_level(logging.ERROR):
                result = storage.load_recent_rolls(chat_id)

        assert result == []
        assert any(
            record.levelno >= logging.ERROR for record in caplog.records
        ), "expected a failure to be logged for a corrupt history file"

    sys.modules.pop("storage", None)
    sys.modules.pop("config", None)


def test_returns_empty_and_logs_when_per_chat_entry_corrupt(caplog):
    """A corrupt per-chat entry yields [] and logs, leaving others intact."""
    chat_id = 42
    other_chat_id = 99

    with tempfile.TemporaryDirectory() as tmpdir:
        data_file = os.path.join(tmpdir, "restaurants.json")
        recent_file = os.path.join(tmpdir, "recent_rolls.json")

        # Valid JSON object, but this chat's entry is not a list of strings.
        # Another chat has a well-formed entry to confirm isolation.
        with open(recent_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    str(chat_id): {"unexpected": "shape"},
                    str(other_chat_id): ["sushi", "tacos"],
                },
                f,
            )

        with pytest.MonkeyPatch().context() as mp:
            storage = _import_storage(mp, data_file, recent_file)

            with caplog.at_level(logging.ERROR):
                result = storage.load_recent_rolls(chat_id)

            # The other chat's well-formed history still loads correctly.
            other = storage.load_recent_rolls(other_chat_id)

        assert result == []
        assert other == ["sushi", "tacos"]
        assert any(
            record.levelno >= logging.ERROR for record in caplog.records
        ), "expected a failure to be logged for a corrupt per-chat entry"

    sys.modules.pop("storage", None)
    sys.modules.pop("config", None)

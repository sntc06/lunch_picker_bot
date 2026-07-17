"""
Property test for storage.py recent-roll history —
Property 9: Recent-roll-history persistence round-trip (bounded).

Validates: Requirements 3a.12, 3a.13, 5.3
"""
import importlib
import os
import sys
import tempfile

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A sequence of roll-result names. Names are stored lowercase by storage, so
# the expected value is computed with .lower() below.
names_strategy = st.lists(st.text(min_size=1, max_size=30), max_size=40)

# Window sizes to trim the history to. 0 keeps no history; larger values may
# exceed the number of appended names (then all names are retained).
window_strategy = st.integers(min_value=0, max_value=50)

# Any chat id; storage keys history by str(chat_id).
chat_id_strategy = st.integers(min_value=1, max_value=10_000)


# ---------------------------------------------------------------------------
# Property 9: Recent-roll-history persistence round-trip (bounded)
# ---------------------------------------------------------------------------

# Feature: telegram-lunch-bot, Property 9: Recent-roll-history persistence
# round-trip (bounded)
@given(chat_id=chat_id_strategy, names=names_strategy, window=window_strategy)
@settings(max_examples=100)
def test_recent_rolls_round_trip(chat_id, names, window):
    """
    **Validates: Requirements 3a.12, 3a.13, 5.3**

    Property 9: For any chat ``c``, any sequence of names ``ns``, and any
    window ``w``, applying ``append_recent_roll(c, ·, w)`` over ``ns`` and
    then performing a fresh ``load_recent_rolls(c)`` (simulating a restart)
    yields the last ``w`` entries of ``ns`` (stored lowercase), most recent
    last.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        data_file = os.path.join(tmpdir, "restaurants.json")
        recent_file = os.path.join(tmpdir, "recent_rolls.json")

        # Ensure a clean import so module-level config reads our temp paths.
        sys.modules.pop("storage", None)
        sys.modules.pop("config", None)

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("BOT_TOKEN", "test-token")
            mp.setenv("DATA_FILE", data_file)
            mp.setenv("RECENT_ROLLS_FILE", recent_file)

            importlib.import_module("config")
            storage = importlib.import_module("storage")

            for name in names:
                storage.append_recent_roll(chat_id, name, window)

            # Simulate a restart: drop the loaded modules and re-import so the
            # fresh load reads history back from disk only.
            sys.modules.pop("storage", None)
            sys.modules.pop("config", None)
            importlib.import_module("config")
            storage = importlib.import_module("storage")

            loaded = storage.load_recent_rolls(chat_id)

        # Names are stored lowercase; history is bounded to the most recent
        # `window` entries (window <= 0 keeps nothing).
        lowered = [name.lower() for name in names]
        expected = lowered[-window:] if window > 0 else []

        assert loaded == expected

    # Clean up cached modules so subsequent tests start fresh.
    sys.modules.pop("storage", None)
    sys.modules.pop("config", None)

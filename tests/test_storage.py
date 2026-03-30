"""
Property test for storage.py — Property 2: Round-trip persistence.

Validates: Requirements 4.1, 5.1, 5.2
"""
import os
import sys
import tempfile

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage_module(data_file: str):
    """Import (or re-import) storage with DATA_FILE pointing at *data_file*."""
    # Remove cached modules so module-level code re-executes with new DATA_FILE.
    sys.modules.pop("storage", None)
    sys.modules.pop("config", None)

    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("BOT_TOKEN", "test-token")
        mp.setenv("DATA_FILE", data_file)
        import importlib
        config = importlib.import_module("config")
        storage = importlib.import_module("storage")

    return storage


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# ISO 8601 timestamps with +08:00 offset, e.g. "2024-01-15T09:30:00+08:00"
iso8601_strategy = st.builds(
    lambda y, mo, d, h, mi, s: f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}+08:00",
    y=st.integers(min_value=2000, max_value=2099),
    mo=st.integers(min_value=1, max_value=12),
    d=st.integers(min_value=1, max_value=28),
    h=st.integers(min_value=0, max_value=23),
    mi=st.integers(min_value=0, max_value=59),
    s=st.integers(min_value=0, max_value=59),
)

restaurant_entry_strategy = st.fixed_dictionaries({
    "name": st.text(min_size=1, max_size=50),
    "added_by": st.text(min_size=1, max_size=50),
    "added_at": iso8601_strategy,
})

restaurant_list_strategy = st.lists(restaurant_entry_strategy, max_size=20)


# ---------------------------------------------------------------------------
# Property 2: Round-trip persistence
# ---------------------------------------------------------------------------

@given(restaurant_list=restaurant_list_strategy)
@settings(max_examples=50)
def test_round_trip_persistence(restaurant_list):
    """
    **Validates: Requirements 4.1, 5.1, 5.2**

    Property 2: For any arbitrary list[dict] L (each dict with `name`,
    `added_by`, `added_at`), assert load(chat_id) equals L after
    save(chat_id, L).
    """
    chat_id = "test_chat_42"

    with tempfile.TemporaryDirectory() as tmpdir:
        data_file = os.path.join(tmpdir, "restaurants.json")

        sys.modules.pop("storage", None)
        sys.modules.pop("config", None)

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("BOT_TOKEN", "test-token")
            mp.setenv("DATA_FILE", data_file)

            import importlib
            importlib.import_module("config")
            storage = importlib.import_module("storage")

            storage.save(chat_id, restaurant_list)
            loaded = storage.load(chat_id)

        assert loaded == restaurant_list

    # Clean up cached modules so subsequent test runs start fresh.
    sys.modules.pop("storage", None)
    sys.modules.pop("config", None)

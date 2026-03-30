"""
Tests for restaurant name handling — casing, CJK characters, and special characters.

Covers:
  - Original casing is preserved on storage round-trip
  - Case-insensitive deduplication
  - Names with CJK characters (e.g. 三商巧福)
  - Names with special characters (e.g. 豬排飯@gogo)
"""

import importlib
import os
import sys
import tempfile

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Point DATA_FILE at a temp file and reload config + storage fresh."""
    data_file = str(tmp_path / "restaurants.json")

    # Reload config with a dummy token and our temp data file
    sys.modules.pop("config", None)
    sys.modules.pop("storage", None)
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("DATA_FILE", data_file)
    importlib.import_module("config")
    importlib.import_module("storage")

    yield

    sys.modules.pop("config", None)
    sys.modules.pop("storage", None)


@pytest.fixture()
def store():
    import storage
    return storage


CHAT_ID = "test_chat_1"

# The three representative names from the spec
SAMPLE_NAMES = [
    "Q Burger",       # mixed-case Latin
    "三商巧福",         # CJK only
    "豬排飯@gogo",      # CJK + special character
]


# ---------------------------------------------------------------------------
# Round-trip: original name is preserved exactly
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", SAMPLE_NAMES)
def test_name_preserved_after_save_and_load(store, name):
    """Saved name must come back byte-for-byte identical."""
    entry = {"name": name, "added_by": "tester", "added_at": "2026-03-30T12:00:00+08:00"}
    store.save(CHAT_ID, [entry])
    loaded = store.load(CHAT_ID)
    assert loaded[0]["name"] == name


# ---------------------------------------------------------------------------
# Deduplication: case variants are rejected, original casing kept
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("original,variant", [
    ("Q Burger", "q burger"),
    ("Q Burger", "Q BURGER"),
    ("Q Burger", "q Burger"),
    # CJK names are identical — same character, same case
    ("三商巧福", "三商巧福"),
    ("豬排飯@gogo", "豬排飯@GOGO"),
    ("豬排飯@gogo", "豬排飯@GoGo"),
])
def test_duplicate_detection_is_case_insensitive(store, original, variant):
    """Adding a case variant of an existing name must be detected as duplicate."""
    store.save(CHAT_ID, [{"name": original, "added_by": "u", "added_at": "2026-03-30T12:00:00+08:00"}])
    restaurants = store.load(CHAT_ID)
    is_duplicate = any(entry["name"].lower() == variant.lower() for entry in restaurants)
    assert is_duplicate, f"Expected '{variant}' to be detected as duplicate of '{original}'"


def test_original_casing_preserved_when_duplicate_rejected(store):
    """After a duplicate attempt, the stored name must still be the original."""
    original = "Q Burger"
    store.save(CHAT_ID, [{"name": original, "added_by": "u", "added_at": "2026-03-30T12:00:00+08:00"}])

    # Simulate what cmd_add does: detect duplicate, do NOT append
    restaurants = store.load(CHAT_ID)
    variant = "q burger"
    if not any(entry["name"].lower() == variant.lower() for entry in restaurants):
        restaurants.append({"name": variant, "added_by": "u", "added_at": "2026-03-30T13:00:00+08:00"})
        store.save(CHAT_ID, restaurants)

    final = store.load(CHAT_ID)
    assert len(final) == 1
    assert final[0]["name"] == original


# ---------------------------------------------------------------------------
# Multiple distinct names coexist correctly
# ---------------------------------------------------------------------------

def test_all_sample_names_stored_and_loaded(store):
    """All three sample names can be stored together and retrieved intact."""
    entries = [
        {"name": n, "added_by": "tester", "added_at": "2026-03-30T12:00:00+08:00"}
        for n in SAMPLE_NAMES
    ]
    store.save(CHAT_ID, entries)
    loaded = store.load(CHAT_ID)
    assert [e["name"] for e in loaded] == SAMPLE_NAMES


# ---------------------------------------------------------------------------
# Remove: case-insensitive match removes the entry, original name gone
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("original,remove_as", [
    ("Q Burger", "q burger"),
    ("Q Burger", "Q BURGER"),
    ("豬排飯@gogo", "豬排飯@GOGO"),
])
def test_remove_is_case_insensitive(store, original, remove_as):
    """Removing by a case variant should delete the entry."""
    store.save(CHAT_ID, [{"name": original, "added_by": "u", "added_at": "2026-03-30T12:00:00+08:00"}])
    restaurants = store.load(CHAT_ID)
    restaurants = [e for e in restaurants if e["name"].lower() != remove_as.lower()]
    store.save(CHAT_ID, restaurants)
    assert store.load(CHAT_ID) == []

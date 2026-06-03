"""
Property test for config.py — Property 5: Config missing token fails fast.

Validates: Requirements 8.5
"""
import importlib
import logging
import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


def _reload_config(env: dict) -> None:
    """Force a fresh import of config under the given environment."""
    # Remove cached module so the module-level code re-executes
    sys.modules.pop("config", None)
    with pytest.MonkeyPatch().context() as mp:
        # Clear all env vars then apply the supplied ones
        mp.delenv("BOT_TOKEN", raising=False)
        mp.delenv("DATA_FILE", raising=False)
        for key, value in env.items():
            mp.setenv(key, value)
        importlib.import_module("config")


# ---------------------------------------------------------------------------
# Property 5: Config missing token fails fast
# ---------------------------------------------------------------------------

@given(st.none())
@settings(max_examples=5)
def test_missing_token_raises_runtime_error(ignored):
    """
    **Validates: Requirements 8.5**

    Property 5: For any execution where BOT_TOKEN is absent from the
    environment, importing config must raise RuntimeError before any
    network call is made.
    """
    sys.modules.pop("config", None)

    with pytest.MonkeyPatch().context() as mp:
        mp.delenv("BOT_TOKEN", raising=False)
        # Also neutralise any .env file by pointing dotenv at a nonexistent path
        mp.setenv("DOTENV_PATH", "/nonexistent/.env")

        with pytest.raises(RuntimeError, match="BOT_TOKEN"):
            importlib.import_module("config")

    # Clean up so other tests start fresh
    sys.modules.pop("config", None)


# ---------------------------------------------------------------------------
# Positive case: token present → no error
# ---------------------------------------------------------------------------

def test_valid_token_does_not_raise():
    """When BOT_TOKEN is set, config imports without error."""
    sys.modules.pop("config", None)

    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("BOT_TOKEN", "test-token-123")
        mp.setenv("DATA_FILE", "data/restaurants.json")
        mod = importlib.import_module("config")
        assert mod.BOT_TOKEN == "test-token-123"

    sys.modules.pop("config", None)


# ---------------------------------------------------------------------------
# LOG_LEVEL parsing
# ---------------------------------------------------------------------------

def _load_parse_log_level():
    """Import config with a valid token and return parse_log_level."""
    sys.modules.pop("config", None)
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("BOT_TOKEN", "test-token-123")
        mod = importlib.import_module("config")
        parse_log_level = mod.parse_log_level
        default = mod.DEFAULT_LOG_LEVEL
    sys.modules.pop("config", None)
    return parse_log_level, default


def test_parse_log_level_known_names():
    """Known level names (case-insensitive) map to logging integers."""
    parse_log_level, _ = _load_parse_log_level()
    assert parse_log_level("debug") == logging.DEBUG
    assert parse_log_level("INFO") == logging.INFO
    assert parse_log_level("Warning") == logging.WARNING
    assert parse_log_level("warn") == logging.WARNING
    assert parse_log_level("ERROR") == logging.ERROR
    assert parse_log_level("critical") == logging.CRITICAL
    assert parse_log_level("  info  ") == logging.INFO


def test_parse_log_level_absent_defaults_to_warning():
    """An absent value falls back to the default (WARNING)."""
    parse_log_level, default = _load_parse_log_level()
    assert default == logging.WARNING
    assert parse_log_level(None) == default


def test_parse_log_level_unrecognised_falls_back_to_default():
    """An unrecognised value falls back to the default rather than raising."""
    parse_log_level, default = _load_parse_log_level()
    assert parse_log_level("nonsense") == default
    assert parse_log_level("") == default

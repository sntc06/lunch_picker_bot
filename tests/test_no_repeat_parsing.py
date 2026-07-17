"""
Property test for config.parse_no_repeat_window — No_Repeat_Window parsing
and default.

# Feature: telegram-lunch-bot, No_Repeat_Window parsing and default

Validates: Requirements 3a.1, 3a.2, 3a.3
"""
import importlib
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Recognised boolean-style tokens, mirroring config.py's backward-compatible
# fallback: truthy → 1, falsy → 0.
TRUE_TOKENS = {"1", "true", "yes", "on"}
FALSE_TOKENS = {"0", "false", "no", "off"}

DEFAULT_WINDOW = 1
WINDOW_MIN = 0
WINDOW_MAX = 1000


def _load_config():
    """Import (or re-import) config with BOT_TOKEN set so it imports cleanly."""
    # config.py raises a RuntimeError at import time if BOT_TOKEN is unset, so
    # set it before importing and drop any cached module first.
    sys.modules.pop("config", None)
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("BOT_TOKEN", "test-token")
        config = importlib.import_module("config")
    return config


def _reference_window(value):
    """Reference implementation of the No_Repeat_Window parsing rules.

    1. Absent (``None``) → default ``1``.
    2. Integer in range ``0``-``1000`` (after strip) → that integer.
    3. Otherwise a boolean-style token (case-insensitive): truthy → ``1``,
       falsy → ``0``.
    4. Any other value → default ``1``.
    """
    if value is None:
        return DEFAULT_WINDOW

    trimmed = value.strip()
    try:
        parsed = int(trimmed)
    except ValueError:
        parsed = None
    if parsed is not None:
        if WINDOW_MIN <= parsed <= WINDOW_MAX:
            return parsed
        return DEFAULT_WINDOW

    normalised = trimmed.lower()
    if normalised in TRUE_TOKENS:
        return 1
    if normalised in FALSE_TOKENS:
        return 0
    return DEFAULT_WINDOW


# ---------------------------------------------------------------------------
# Property: parsing matches the reference rules for arbitrary text
# ---------------------------------------------------------------------------

@given(st.text())
@settings(max_examples=200)
def test_parse_window_matches_reference(value):
    """
    **Validates: Requirements 3a.1, 3a.2, 3a.3**

    For any input string, ``parse_no_repeat_window`` returns an int that
    matches the reference parsing rules.
    """
    config = _load_config()
    result = config.parse_no_repeat_window(value)
    assert isinstance(result, int)
    assert result == _reference_window(value)


# ---------------------------------------------------------------------------
# Property: any integer in range round-trips exactly
# ---------------------------------------------------------------------------

@given(
    n=st.integers(min_value=WINDOW_MIN, max_value=WINDOW_MAX),
    lead=st.integers(min_value=0, max_value=3),
    trail=st.integers(min_value=0, max_value=3),
)
@settings(max_examples=200)
def test_in_range_integers_round_trip(n, lead, trail):
    """An integer within 0-1000 (with surrounding whitespace) parses to itself."""
    config = _load_config()
    raw = (" " * lead) + str(n) + (" " * trail)
    assert config.parse_no_repeat_window(raw) == n


# ---------------------------------------------------------------------------
# Property: out-of-range integers fall back to the default
# ---------------------------------------------------------------------------

@given(
    n=st.integers().filter(lambda x: x < WINDOW_MIN or x > WINDOW_MAX),
)
@settings(max_examples=200)
def test_out_of_range_integers_default(n):
    """An integer outside 0-1000 falls back to the default (1)."""
    config = _load_config()
    assert config.parse_no_repeat_window(str(n)) == DEFAULT_WINDOW


# ---------------------------------------------------------------------------
# Absent value defaults to 1
# ---------------------------------------------------------------------------

def test_parse_window_none_defaults_to_one():
    """
    **Validates: Requirements 3a.1**

    An absent value (``None``) defaults to ``1``.
    """
    config = _load_config()
    assert config.parse_no_repeat_window(None) == DEFAULT_WINDOW


# ---------------------------------------------------------------------------
# Backward-compatible boolean-style tokens
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", sorted(TRUE_TOKENS - {"1"}))
@pytest.mark.parametrize("transform", [
    lambda s: s,
    lambda s: s.upper(),
    lambda s: s.capitalize(),
    lambda s: f"  {s}  ",
    lambda s: f"\t{s.upper()}\n",
])
def test_truthy_tokens_map_to_one(token, transform):
    """Each recognised truthy token → 1 regardless of case/whitespace."""
    config = _load_config()
    assert config.parse_no_repeat_window(transform(token)) == 1


@pytest.mark.parametrize("token", sorted(FALSE_TOKENS - {"0"}))
@pytest.mark.parametrize("transform", [
    lambda s: s,
    lambda s: s.upper(),
    lambda s: s.capitalize(),
    lambda s: f"  {s}  ",
    lambda s: f"\t{s.upper()}\n",
])
def test_falsy_tokens_map_to_zero(token, transform):
    """Each recognised falsy token → 0 regardless of case/whitespace."""
    config = _load_config()
    assert config.parse_no_repeat_window(transform(token)) == 0


# ---------------------------------------------------------------------------
# Unrecognised non-integer strings fall back to the default
# ---------------------------------------------------------------------------

@given(st.text())
@settings(max_examples=200)
def test_unrecognised_strings_default_to_one(value):
    """
    **Validates: Requirements 3a.1, 3a.3**

    Strings that are neither an in-range integer nor a recognised
    boolean-style token fall back to the default (``1``).
    """
    trimmed = value.strip()
    # Filter out anything the parser would legitimately recognise.
    try:
        int(trimmed)
        return  # integer-like: covered by the range tests
    except ValueError:
        pass
    if trimmed.lower() in TRUE_TOKENS or trimmed.lower() in FALSE_TOKENS:
        return  # recognised token: covered by the token tests
    config = _load_config()
    assert config.parse_no_repeat_window(value) == DEFAULT_WINDOW

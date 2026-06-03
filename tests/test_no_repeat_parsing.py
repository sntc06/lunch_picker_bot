"""
Property test for config.parse_no_repeat — Property 10:
No_Repeat_Toggle parsing and default.

# Feature: telegram-lunch-bot, Property 10: No_Repeat_Toggle parsing and default

Validates: Requirements 3a.1
"""
import importlib
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Recognised tokens, mirroring config.py's truthy/falsy convention.
TRUE_TOKENS = {"1", "true", "yes", "on"}
FALSE_TOKENS = {"0", "false", "no", "off"}


def _load_config():
    """Import (or re-import) config with BOT_TOKEN set so it imports cleanly."""
    # config.py raises a RuntimeError at import time if BOT_TOKEN is unset, so
    # set it before importing and drop any cached module first.
    sys.modules.pop("config", None)
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("BOT_TOKEN", "test-token")
        config = importlib.import_module("config")
    return config


def _reference_truthy(value):
    """Reference implementation of the truthy/falsy convention.

    ``1/true/yes/on`` → True, ``0/false/no/off`` → False (case-insensitive,
    surrounding whitespace stripped). Absent (``None``) → True (default
    enabled). Any UNRECOGNISED value falls back to the default (True).
    """
    if value is None:
        return True
    normalised = value.strip().lower()
    if normalised in TRUE_TOKENS:
        return True
    if normalised in FALSE_TOKENS:
        return False
    return True


# A strategy that builds recognised tokens with random casing and surrounding
# whitespace, to exercise the case-insensitive + strip behaviour.
def _decorate(token):
    return st.builds(
        lambda tok, lead, trail, upper: (
            (" " * lead) + (tok.upper() if upper else tok) + (" " * trail)
        ),
        tok=st.just(token),
        lead=st.integers(min_value=0, max_value=3),
        trail=st.integers(min_value=0, max_value=3),
        upper=st.booleans(),
    )


_known_token_strategy = st.one_of(
    *[_decorate(t) for t in sorted(TRUE_TOKENS | FALSE_TOKENS)]
)


# ---------------------------------------------------------------------------
# Property 10: parsing matches the truthy/falsy convention
# ---------------------------------------------------------------------------

@given(st.text())
@settings(max_examples=200)
def test_parse_no_repeat_matches_convention(value):
    """
    **Validates: Requirements 3a.1**

    Property 10: For any input string, ``parse_no_repeat`` returns a bool
    that matches the truthy/falsy convention. Random text is handled by the
    reference implementation rather than assumed to be unrecognised, since
    ``st.text()`` could occasionally produce a recognised token.
    """
    config = _load_config()
    result = config.parse_no_repeat(value)
    assert isinstance(result, bool)
    assert result == _reference_truthy(value)


@given(_known_token_strategy)
@settings(max_examples=200)
def test_parse_no_repeat_handles_case_and_whitespace(value):
    """
    **Validates: Requirements 3a.1**

    Property 10: Recognised tokens with arbitrary casing and surrounding
    whitespace parse to the same boolean as the reference convention.
    """
    config = _load_config()
    assert config.parse_no_repeat(value) == _reference_truthy(value)


# ---------------------------------------------------------------------------
# Property 10: absent value defaults to enabled (True)
# ---------------------------------------------------------------------------

def test_parse_no_repeat_none_defaults_to_true():
    """
    **Validates: Requirements 3a.1**

    Property 10: An absent value (``None``) defaults to enabled (``True``).
    """
    config = _load_config()
    assert config.parse_no_repeat(None) is True


# ---------------------------------------------------------------------------
# Explicit example assertions for each recognised token
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", sorted(TRUE_TOKENS))
@pytest.mark.parametrize("transform", [
    lambda s: s,
    lambda s: s.upper(),
    lambda s: s.capitalize(),
    lambda s: f"  {s}  ",
    lambda s: f"\t{s.upper()}\n",
])
def test_recognised_true_tokens(token, transform):
    """Each recognised true token → True regardless of case/whitespace."""
    config = _load_config()
    assert config.parse_no_repeat(transform(token)) is True


@pytest.mark.parametrize("token", sorted(FALSE_TOKENS))
@pytest.mark.parametrize("transform", [
    lambda s: s,
    lambda s: s.upper(),
    lambda s: s.capitalize(),
    lambda s: f"  {s}  ",
    lambda s: f"\t{s.upper()}\n",
])
def test_recognised_false_tokens(token, transform):
    """Each recognised false token → False regardless of case/whitespace."""
    config = _load_config()
    assert config.parse_no_repeat(transform(token)) is False


# ---------------------------------------------------------------------------
# Property 10: unrecognised strings fall back to the default (True)
# ---------------------------------------------------------------------------

@given(st.text())
@settings(max_examples=200)
def test_unrecognised_strings_default_to_true(value):
    """
    **Validates: Requirements 3a.1**

    Property 10: Strings that are not recognised tokens (after strip+lower)
    fall back to the default (``True``). Recognised tokens are filtered out
    so the assertion targets the unrecognised case specifically.
    """
    normalised = value.strip().lower()
    if normalised in TRUE_TOKENS or normalised in FALSE_TOKENS:
        # Not an unrecognised value — skip; covered by the convention test.
        return
    config = _load_config()
    assert config.parse_no_repeat(value) is True

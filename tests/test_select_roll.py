"""
Property tests for the pure ``select_roll`` helper in ``bot.py``.

Covers the roll-selection correctness properties from the design document:

  - Property 3: Uniform random selection            (Req 3.3)
  - Property 4: Roll result is always from the list  (Req 3.1)
  - Property 5: No-repeat avoids the previous result (Req 3a.3, 3a.4)
  - Property 6: Full-list eligibility when no-repeat does not constrain
                                                     (Req 3a.5, 3a.6, 3a.7)
  - Property 9: Bounded selection                    (Req 3a.11)

``select_roll`` is a pure function (no Telegram or storage I/O), so it can be
exercised directly. ``bot`` imports ``storage`` → ``config``, and ``config``
requires ``BOT_TOKEN`` at import time; we set a dummy token before importing
so the module loads cleanly. ``select_roll`` itself never touches config or
storage at call time — it only uses ``random`` — so the dummy token does not
affect any assertions below.

Note: ``previous`` is the *lowercase* form of a restaurant name (or ``None``),
matching how ``storage.save_previous_roll`` stores it. In the real system
restaurant names are deduplicated case-insensitively (Req 1.5), so the
generators below produce lists whose names are unique when lower-cased, and
any "present" ``previous`` value is derived from an entry's name lower-cased.
"""
import os
import random

from hypothesis import given, settings
from hypothesis import strategies as st

# config (imported transitively by bot) needs BOT_TOKEN at import time.
os.environ.setdefault("BOT_TOKEN", "test-token")
import bot  # noqa: E402


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A simple alphabet that mixes letter cases so case-insensitive logic is
# meaningfully exercised, plus digits for variety.
_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

name_strategy = st.text(alphabet=_ALPHABET, min_size=1, max_size=10)


def _entry(name: str) -> dict:
    """Build a realistic restaurant entry dict from a name."""
    return {"name": name, "added_by": "tester", "added_at": "2026-01-01T12:00:00+08:00"}


# Restaurant lists whose names are unique case-insensitively (the real-system
# invariant from Req 1.5). Returns a list of entry dicts.
restaurants_strategy = st.lists(
    name_strategy,
    min_size=1,
    max_size=8,
    unique_by=lambda s: s.lower(),
).map(lambda names: [_entry(n) for n in names])


@st.composite
def list_toggle_prev(draw):
    """A list plus an arbitrary (toggle, previous) combination.

    ``previous`` is one of: ``None``, the lower-cased name of an entry that is
    present in the list, or an arbitrary lower-cased string (which may or may
    not coincide with a list name). ``no_repeat`` is an arbitrary boolean.
    """
    restaurants = draw(restaurants_strategy)
    names_lower = [e["name"].lower() for e in restaurants]
    previous = draw(
        st.one_of(
            st.none(),
            st.sampled_from(names_lower),
            name_strategy.map(str.lower),
        )
    )
    no_repeat = draw(st.booleans())
    return restaurants, previous, no_repeat


@st.composite
def list_with_present_prev(draw):
    """A list together with a ``previous`` that is present in the list.

    ``previous`` is the lower-cased name of one of the entries, mirroring how
    a real ``Previous_Roll_Result`` would be stored.
    """
    restaurants = draw(restaurants_strategy)
    names_lower = [e["name"].lower() for e in restaurants]
    previous = draw(st.sampled_from(names_lower))
    return restaurants, previous


@st.composite
def unconstrained(draw):
    """A list plus a (previous, no_repeat) combination where the no-repeat
    exclusion does NOT apply: toggle disabled, OR previous is None, OR
    previous is not present in the list."""
    restaurants = draw(restaurants_strategy)
    names_lower = [e["name"].lower() for e in restaurants]
    scenario = draw(st.sampled_from(["toggle_off", "prev_none", "prev_absent"]))

    if scenario == "toggle_off":
        no_repeat = False
        previous = draw(
            st.one_of(
                st.none(),
                st.sampled_from(names_lower),
                name_strategy.map(str.lower),
            )
        )
    elif scenario == "prev_none":
        no_repeat = True
        previous = None
    else:  # prev_absent — previous is set but not present in the list
        no_repeat = True
        previous = draw(
            name_strategy.map(str.lower).filter(lambda s: s not in names_lower)
        )

    return restaurants, previous, no_repeat


# ---------------------------------------------------------------------------
# Property 4: Roll result is always from the list
# ---------------------------------------------------------------------------

# Feature: telegram-lunch-bot, Property 4: Roll result is always from the list
@given(list_toggle_prev())
@settings(max_examples=200)
def test_property_4_result_always_from_list(data):
    """
    **Validates: Requirements 3.1**

    Property 4: For any non-empty list and any toggle/previous combination,
    ``select_roll`` returns a member of the list.
    """
    restaurants, previous, no_repeat = data
    result = bot.select_roll(restaurants, previous, no_repeat)
    assert result in restaurants


# ---------------------------------------------------------------------------
# Property 3: Uniform random selection
# ---------------------------------------------------------------------------

# Feature: telegram-lunch-bot, Property 3: Uniform random selection
@given(
    k=st.integers(min_value=2, max_value=6),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
@settings(max_examples=100, deadline=None)
def test_property_3_uniform_selection(k, seed):
    """
    **Validates: Requirements 3.3**

    Property 3: With the No_Repeat_Toggle disabled, over a large number of
    rolls on a list of ``k`` items each item appears with frequency
    approximately ``1/k`` (within tolerance).
    """
    restaurants = [_entry(f"r{i}") for i in range(k)]
    n_rolls = 3000

    random.seed(seed)
    counts = {e["name"]: 0 for e in restaurants}
    for _ in range(n_rolls):
        pick = bot.select_roll(restaurants, previous=None, no_repeat=False)
        counts[pick["name"]] += 1

    expected = n_rolls / k
    tolerance = 0.2 * expected  # generous band; uniform draws stay well inside
    for name, count in counts.items():
        assert abs(count - expected) <= tolerance, (
            f"name={name!r} count={count} expected≈{expected:.1f} "
            f"(k={k}, seed={seed})"
        )


# ---------------------------------------------------------------------------
# Property 5: No-repeat avoids the previous result
# ---------------------------------------------------------------------------

# Feature: telegram-lunch-bot, Property 5: No-repeat avoids the previous result
@given(list_with_present_prev())
@settings(max_examples=200)
def test_property_5_no_repeat_avoids_previous(data):
    """
    **Validates: Requirements 3a.3, 3a.4**

    Property 5: With the No_Repeat_Toggle enabled and ``previous`` present in
    the list: if the list has two or more entries the result is in the list
    and not equal to ``previous``; if the list has exactly one entry that
    single entry is returned (graceful degradation).
    """
    restaurants, previous = data
    result = bot.select_roll(restaurants, previous, no_repeat=True)

    if len(restaurants) >= 2:
        assert result in restaurants
        assert result["name"].lower() != previous
    else:
        assert result == restaurants[0]


# ---------------------------------------------------------------------------
# Property 6: Full-list eligibility when no-repeat does not constrain
# ---------------------------------------------------------------------------

# Feature: telegram-lunch-bot, Property 6: Full-list eligibility when no-repeat does not constrain
@given(data=unconstrained(), seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=150, deadline=None)
def test_property_6_full_list_eligibility(data, seed):
    """
    **Validates: Requirements 3a.5, 3a.6, 3a.7**

    Property 6: When the no-repeat exclusion does not apply (toggle disabled,
    OR previous is None, OR previous not in the list), the result comes from
    the entire list and, over many rolls, every element is reachable.
    """
    restaurants, previous, no_repeat = data
    names = {e["name"] for e in restaurants}

    # Single roll: result is from the entire list.
    single = bot.select_roll(restaurants, previous, no_repeat)
    assert single in restaurants

    # Many rolls: every element of the list is reachable.
    random.seed(seed)
    seen = set()
    n_rolls = 100 * len(restaurants)
    for _ in range(n_rolls):
        pick = bot.select_roll(restaurants, previous, no_repeat)
        assert pick in restaurants
        seen.add(pick["name"])

    assert seen == names, f"unreachable elements: {names - seen}"


# ---------------------------------------------------------------------------
# Property 9: Bounded selection
# ---------------------------------------------------------------------------

# Feature: telegram-lunch-bot, Property 9: Bounded selection
@given(list_toggle_prev())
@settings(max_examples=200)
def test_property_9_bounded_selection(data):
    """
    **Validates: Requirements 3a.11**

    Property 9: For any non-empty list and any toggle/previous combination,
    the candidate set is non-empty and ``select_roll`` returns exactly one
    element of the list (no looping or indefinite retry — the call simply
    returns a single entry).
    """
    restaurants, previous, no_repeat = data
    result = bot.select_roll(restaurants, previous, no_repeat)

    # Exactly one entry is returned, and it is a member of the list (a
    # non-empty candidate set is implied by a successful single return).
    assert isinstance(result, dict)
    assert result in restaurants
    assert sum(1 for e in restaurants if e is result) == 1

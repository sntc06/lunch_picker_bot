"""
Tests for the pure ``select_roll`` helper in ``bot.py``.

These are the pre-existing selection tests, updated for the new
``select_roll(restaurants, recent_history, no_repeat_window)`` signature and
its window/relaxation semantics (see design.md). The full property suite for
the new design (Properties 3–8) is implemented by dedicated test tasks; the
tests here preserve the original coverage:

  - result is always a member of the list          (Req 3.1)
  - uniform random selection with window 0         (Req 3.3, 3a.5)
  - window 1 avoids the single most recent result  (Req 3a.6, 3a.9)
  - full-list eligibility when unconstrained       (Req 3a.5, 3a.10, 3a.11)
  - bounded selection                              (Req 3a.15)

``select_roll`` is a pure function (no Telegram or storage I/O), so it can be
exercised directly. ``bot`` imports ``storage`` → ``config``, and ``config``
requires ``BOT_TOKEN`` at import time; we set a dummy token before importing
so the module loads cleanly. ``select_roll`` itself never touches config or
storage at call time — it only uses ``random`` — so the dummy token does not
affect any assertions below.

Note: ``recent_history`` holds *lowercase* result names, most recent last,
matching how ``storage`` persists the Recent_Roll_History. Restaurant names
are deduplicated case-insensitively (Req 1.5), so the generators below
produce lists whose names are unique when lower-cased, and any "present"
history entry is derived from an entry's name lower-cased.
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
def list_window_history(draw):
    """A list plus an arbitrary (recent_history, no_repeat_window) combination.

    History entries are lowercase names that may be present in the list,
    absent from it, or a mix; the window ranges from 0 to beyond the list
    size and the history length.
    """
    restaurants = draw(restaurants_strategy)
    names_lower = [e["name"].lower() for e in restaurants]
    history = draw(
        st.lists(
            st.one_of(st.sampled_from(names_lower), name_strategy.map(str.lower)),
            min_size=0,
            max_size=12,
        )
    )
    window = draw(st.integers(min_value=0, max_value=12))
    return restaurants, history, window


@st.composite
def list_with_present_prev(draw):
    """A multi-entry list together with a most-recent result present in it.

    The history's last entry is the lower-cased name of one of the entries,
    mirroring how a real Recent_Roll_History would be stored.
    """
    restaurants = draw(restaurants_strategy.filter(lambda r: len(r) >= 2))
    names_lower = [e["name"].lower() for e in restaurants]
    previous = draw(st.sampled_from(names_lower))
    return restaurants, previous


@st.composite
def unconstrained(draw):
    """A list plus (history, window) where the exclusion does NOT apply:
    window 0, OR empty history, OR every effective-window name absent from
    the list."""
    restaurants = draw(restaurants_strategy)
    names_lower = {e["name"].lower() for e in restaurants}
    scenario = draw(st.sampled_from(["window_zero", "history_empty", "names_absent"]))

    if scenario == "window_zero":
        window = 0
        history = draw(
            st.lists(name_strategy.map(str.lower), min_size=0, max_size=6)
        )
    elif scenario == "history_empty":
        window = draw(st.integers(min_value=1, max_value=6))
        history = []
    else:  # names_absent — history entries are not present in the list
        window = draw(st.integers(min_value=1, max_value=6))
        history = draw(
            st.lists(
                name_strategy.map(str.lower).filter(lambda s: s not in names_lower),
                min_size=1,
                max_size=6,
            )
        )

    return restaurants, history, window


# ---------------------------------------------------------------------------
# Result is always from the list
# ---------------------------------------------------------------------------

@given(list_window_history())
@settings(max_examples=200)
def test_result_always_from_list(data):
    """
    **Validates: Requirements 3.1**

    For any non-empty list and any history/window combination,
    ``select_roll`` returns a member of the list.
    """
    restaurants, history, window = data
    result = bot.select_roll(restaurants, history, window)
    assert result in restaurants


# ---------------------------------------------------------------------------
# Uniform random selection with window 0
# ---------------------------------------------------------------------------

@given(
    k=st.integers(min_value=2, max_value=6),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
@settings(max_examples=100, deadline=None)
def test_uniform_selection_window_zero(k, seed):
    """
    **Validates: Requirements 3.3, 3a.5**

    With a No_Repeat_Window of 0, over a large number of rolls on a list of
    ``k`` items each item appears with frequency approximately ``1/k``
    (within tolerance).
    """
    restaurants = [_entry(f"r{i}") for i in range(k)]
    n_rolls = 3000

    random.seed(seed)
    counts = {e["name"]: 0 for e in restaurants}
    for _ in range(n_rolls):
        pick = bot.select_roll(restaurants, [], 0)
        counts[pick["name"]] += 1

    expected = n_rolls / k
    tolerance = 0.2 * expected  # generous band; uniform draws stay well inside
    for name, count in counts.items():
        assert abs(count - expected) <= tolerance, (
            f"name={name!r} count={count} expected≈{expected:.1f} "
            f"(k={k}, seed={seed})"
        )


# ---------------------------------------------------------------------------
# Window 1 avoids the single most recent result
# ---------------------------------------------------------------------------

@given(list_with_present_prev())
@settings(max_examples=200)
def test_window_one_avoids_previous(data):
    """
    **Validates: Requirements 3a.6, 3a.9**

    With a No_Repeat_Window of 1 and the most recent result present in a
    list of two or more entries, the result is in the list and not equal to
    that most recent result. A single-restaurant list always returns its
    only entry.
    """
    restaurants, previous = data
    result = bot.select_roll(restaurants, [previous], 1)

    assert result in restaurants
    assert result["name"].lower() != previous


@given(name_strategy, st.integers(min_value=1, max_value=6))
@settings(max_examples=100)
def test_single_restaurant_always_returned(name, window):
    """
    **Validates: Requirements 3a.9**

    With a No_Repeat_Window of 1 or greater, a single-restaurant list always
    returns that restaurant, even when its name fills the recent history.
    """
    restaurants = [_entry(name)]
    history = [name.lower()] * window
    assert bot.select_roll(restaurants, history, window) == restaurants[0]


# ---------------------------------------------------------------------------
# Full-list eligibility when the window does not constrain
# ---------------------------------------------------------------------------

@given(data=unconstrained(), seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=150, deadline=None)
def test_full_list_eligibility(data, seed):
    """
    **Validates: Requirements 3a.5, 3a.10, 3a.11**

    When the exclusion does not apply (window 0, OR empty history, OR every
    history name absent from the list), the result comes from the entire
    list and, over many rolls, every element is reachable.
    """
    restaurants, history, window = data
    names = {e["name"] for e in restaurants}

    # Single roll: result is from the entire list.
    single = bot.select_roll(restaurants, history, window)
    assert single in restaurants

    # Many rolls: every element of the list is reachable.
    random.seed(seed)
    seen = set()
    n_rolls = 100 * len(restaurants)
    for _ in range(n_rolls):
        pick = bot.select_roll(restaurants, history, window)
        assert pick in restaurants
        seen.add(pick["name"])

    assert seen == names, f"unreachable elements: {names - seen}"


# ---------------------------------------------------------------------------
# Bounded selection
# ---------------------------------------------------------------------------

@given(list_window_history())
@settings(max_examples=200)
def test_bounded_selection(data):
    """
    **Validates: Requirements 3a.15**

    For any non-empty list and any history/window combination (including a
    window that covers every name in the list), ``select_roll`` terminates
    and returns exactly one element of the list — no unbounded retry loop.
    """
    restaurants, history, window = data
    result = bot.select_roll(restaurants, history, window)

    # Exactly one entry is returned, and it is a member of the list (a
    # non-empty candidate set is implied by a successful single return).
    assert isinstance(result, dict)
    assert result in restaurants
    assert sum(1 for e in restaurants if e is result) == 1

import os
from dotenv import load_dotenv

load_dotenv()

# Truthy/falsy tokens for parsing boolean-style environment flags
# (case-insensitive). Anything not listed falls back to the default.
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def parse_no_repeat(value: str | None) -> bool:
    """Parse the NO_REPEAT flag into a boolean.

    Uses the usual truthy/falsy convention (case-insensitive):
    ``1/true/yes/on`` → ``True`` and ``0/false/no/off`` → ``False``.
    An absent value (``None``) defaults to ``True`` (enabled). Any
    unrecognised value falls back to the default (``True``) rather than
    raising, so a typo never prevents startup.

    This is a pure function so it can be property-tested in isolation.
    """
    if value is None:
        return True
    normalised = value.strip().lower()
    if normalised in _TRUE_VALUES:
        return True
    if normalised in _FALSE_VALUES:
        return False
    return True


BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DATA_FILE: str = os.getenv("DATA_FILE", "data/restaurants.json")

# Previous-roll file lives in the same data folder as DATA_FILE. By default
# it is `previous_roll.json` beside DATA_FILE; it can be overridden via env.
PREVIOUS_ROLL_FILE: str = os.getenv(
    "PREVIOUS_ROLL_FILE",
    os.path.join(os.path.dirname(DATA_FILE), "previous_roll.json"),
)

# No_Repeat_Toggle: read once at startup and constant for the process
# lifetime (no runtime mutation path). Defaults to enabled when absent.
NO_REPEAT: bool = parse_no_repeat(os.getenv("NO_REPEAT"))

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. "
        "Please set it in your environment or in a .env file."
    )

import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Default No_Repeat_Window used when NO_REPEAT_WINDOW is absent, out of range,
# or otherwise unparseable. `1` excludes only the single most recent result.
DEFAULT_NO_REPEAT_WINDOW = 1

# Inclusive bounds for the accepted No_Repeat_Window integer range.
_NO_REPEAT_WINDOW_MIN = 0
_NO_REPEAT_WINDOW_MAX = 1000

# Truthy/falsy tokens for parsing boolean-style environment flags
# (case-insensitive). Anything not listed falls back to the default.
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

# Default log level used when LOG_LEVEL is absent or unrecognised. WARNING
# keeps the journal quiet by suppressing httpx's per-request INFO lines while
# still recording the handlers' ERROR-level logs.
DEFAULT_LOG_LEVEL = logging.WARNING

# Accepted log level names, mapped to their logging module integer values.
_LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def parse_no_repeat_window(raw: str | None) -> int:
    """Parse the NO_REPEAT_WINDOW flag into an integer window count.

    Rules (Req 3a.1, 3a.2, 3a.3):

    1. Absent (``None``) → the default ``1``.
    2. A trimmed value that parses as an integer in range ``0``–``1000``
       inclusive → that integer.
    3. Otherwise a supported boolean-style token (case-insensitive), kept for
       backward compatibility: ``true``/``yes``/``on`` → ``1`` and
       ``false``/``no``/``off`` → ``0``.
    4. Any other value — a non-integer, an out-of-range integer, or an
       unrecognised token — falls back to the default ``1`` while logging a
       warning and continuing startup (never raising).

    This is a pure function so it can be property-tested in isolation.
    """
    if raw is None:
        return DEFAULT_NO_REPEAT_WINDOW

    trimmed = raw.strip()

    # Rule 2: integer within the accepted range.
    try:
        parsed = int(trimmed)
    except ValueError:
        parsed = None
    if parsed is not None:
        if _NO_REPEAT_WINDOW_MIN <= parsed <= _NO_REPEAT_WINDOW_MAX:
            return parsed
        logger.warning(
            "NO_REPEAT_WINDOW=%r is out of range %d-%d; using default %d.",
            raw,
            _NO_REPEAT_WINDOW_MIN,
            _NO_REPEAT_WINDOW_MAX,
            DEFAULT_NO_REPEAT_WINDOW,
        )
        return DEFAULT_NO_REPEAT_WINDOW

    # Rule 3: boolean-style token fallback (case-insensitive).
    normalised = trimmed.lower()
    if normalised in _TRUE_VALUES:
        return 1
    if normalised in _FALSE_VALUES:
        return 0

    # Rule 4: unrecognised value → default, log and continue.
    logger.warning(
        "NO_REPEAT_WINDOW=%r is not a valid integer or boolean token; "
        "using default %d.",
        raw,
        DEFAULT_NO_REPEAT_WINDOW,
    )
    return DEFAULT_NO_REPEAT_WINDOW


def parse_log_level(value: str | None) -> int:
    """Parse the LOG_LEVEL flag into a ``logging`` level integer.

    Accepts standard level names (case-insensitive): ``CRITICAL``, ``ERROR``,
    ``WARNING`` (alias ``WARN``), ``INFO``, ``DEBUG``. An absent value
    (``None``) or any unrecognised value falls back to ``DEFAULT_LOG_LEVEL``
    (``WARNING``) rather than raising, so a typo never prevents startup.

    This is a pure function so it can be tested in isolation.
    """
    if value is None:
        return DEFAULT_LOG_LEVEL
    return _LOG_LEVELS.get(value.strip().upper(), DEFAULT_LOG_LEVEL)


BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DATA_FILE: str = os.getenv("DATA_FILE", "data/restaurants.json")

# Recent-roll history file lives in the same data folder as DATA_FILE. By
# default it is `recent_rolls.json` beside DATA_FILE; it can be overridden via
# env. Kept separate from DATA_FILE so restaurants.json needs no migration.
RECENT_ROLLS_FILE: str = os.getenv(
    "RECENT_ROLLS_FILE",
    os.path.join(os.path.dirname(DATA_FILE), "recent_rolls.json"),
)

# No_Repeat_Window: integer count of most-recent roll results to exclude on
# the next roll. Read once at startup and constant for the process lifetime
# (no runtime mutation path). Defaults to 1 when absent or unparseable.
NO_REPEAT_WINDOW: int = parse_no_repeat_window(os.getenv("NO_REPEAT_WINDOW"))

# Logging verbosity, read once at startup. Defaults to WARNING to keep the
# journal quiet; set LOG_LEVEL=INFO or DEBUG in the environment / .env for
# more detail when debugging.
LOG_LEVEL: int = parse_log_level(os.getenv("LOG_LEVEL"))

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. "
        "Please set it in your environment or in a .env file."
    )

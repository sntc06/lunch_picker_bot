"""
Bug-condition exploration test for the "ignore reply messages" bugfix.

Property 1 (Bug Condition): reply messages that reach ``cmd_unknown`` (plain
text or an unrecognised command) must be ignored — ``cmd_unknown`` must NOT
call ``update.message.reply_text``.

    isBugCondition(input) == (input.message.reply_to_message IS NOT None)

This test encodes the EXPECTED behaviour (no response). It is EXPECTED TO FAIL
on the unfixed code, because the current ``cmd_unknown`` always calls
``reply_text(messages.HELP_TEXT)`` regardless of ``reply_to_message``. That
failure confirms the bug exists. After the fix (early-return guard on
``reply_to_message``) this same test will pass.

``bot`` imports ``storage`` → ``config``, and ``config`` requires ``BOT_TOKEN``
at import time; we set a dummy token before importing so the module loads
cleanly, mirroring ``tests/test_select_roll.py``.
"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

# config (imported transitively by bot) needs BOT_TOKEN at import time.
os.environ.setdefault("BOT_TOKEN", "test-token")
import bot  # noqa: E402
import messages  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_reply_update(text: str) -> MagicMock:
    """Build a mock ``Update`` for a message that IS a reply.

    ``message.reply_to_message`` is set to a truthy mock ``Message`` (so the
    bug condition holds) and ``message.reply_text`` is an ``AsyncMock`` so we
    can assert whether the handler responded.
    """
    update = MagicMock(name="Update")
    update.message = MagicMock(name="Message")
    update.message.text = text
    # Truthy replied-to message → bug condition holds.
    update.message.reply_to_message = MagicMock(name="RepliedToMessage")
    update.message.reply_text = AsyncMock(name="reply_text")
    return update


def make_non_reply_update(text: str) -> MagicMock:
    """Build a mock ``Update`` for a message that is NOT a reply.

    ``message.reply_to_message`` is ``None`` (so ``isBugCondition`` returns
    false) and ``message.reply_text`` is an ``AsyncMock`` so we can assert the
    handler responded with exactly one ``HELP_TEXT`` call.
    """
    update = MagicMock(name="Update")
    update.message = MagicMock(name="Message")
    update.message.text = text
    # Not a reply → bug condition does NOT hold.
    update.message.reply_to_message = None
    update.message.reply_text = AsyncMock(name="reply_text")
    return update


def make_context() -> MagicMock:
    """Build a mock ``ContextTypes.DEFAULT_TYPE``."""
    return MagicMock(name="Context")


# Message text: both plain text and unknown-command strings (e.g. "/thanks").
_ALPHABET = "abcdefghijklmnopqrstuvwxyz "
message_text_strategy = st.one_of(
    st.text(alphabet=_ALPHABET, min_size=0, max_size=40),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20).map(
        lambda s: "/" + s
    ),
)


# ---------------------------------------------------------------------------
# Property 1: Bug Condition — reply messages to the catch-all are ignored
# ---------------------------------------------------------------------------

# Feature: ignore-reply-messages, Property 1: Bug Condition - reply messages ignored
@given(text=message_text_strategy)
@settings(max_examples=200)
def test_property_1_reply_messages_are_ignored(text):
    """
    **Validates: Requirements 1.1, 1.2, 2.1, 2.2**

    Property 1 (Bug Condition): for any message text (plain text or an
    unknown-command string) whose ``reply_to_message`` is set, invoking
    ``cmd_unknown`` produces NO response — ``reply_text`` is never called.

    EXPECTED TO FAIL on unfixed code: the current ``cmd_unknown`` calls
    ``reply_text(HELP_TEXT)`` even when the message is a reply.
    """
    update = make_reply_update(text)
    context = make_context()

    asyncio.run(bot.cmd_unknown(update, context))

    update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# Concrete counterexample cases from the design document
# ---------------------------------------------------------------------------

def test_plain_text_reply_is_ignored():
    """Concrete case (Req 2.1): plain-text reply "sounds good" → no response.

    EXPECTED TO FAIL on unfixed code.
    """
    update = make_reply_update("sounds good")
    context = make_context()

    asyncio.run(bot.cmd_unknown(update, context))

    update.message.reply_text.assert_not_called()


def test_unknown_command_reply_is_ignored():
    """Concrete case (Req 2.2): unknown-command reply "/thanks" → no response.

    EXPECTED TO FAIL on unfixed code.
    """
    update = make_reply_update("/thanks")
    context = make_context()

    asyncio.run(bot.cmd_unknown(update, context))

    update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# Property 2: Preservation — non-reply messages still receive HELP_TEXT
# ---------------------------------------------------------------------------

# Feature: ignore-reply-messages, Property 2: Preservation - non-reply messages get HELP_TEXT
@given(text=message_text_strategy)
@settings(max_examples=200)
def test_property_2_non_reply_messages_receive_help_text(text):
    """
    **Validates: Requirements 3.1, 3.2**

    Property 2 (Preservation): for any message text (plain text or an
    unknown-command string) whose ``reply_to_message`` is ``None``, invoking
    ``cmd_unknown`` produces exactly one ``reply_text(messages.HELP_TEXT)``
    call — preserving the existing help-text behaviour for non-reply plain
    text and non-reply unrecognised commands.

    EXPECTED TO PASS on unfixed code: this establishes the baseline behaviour
    that the fix must preserve.
    """
    update = make_non_reply_update(text)
    context = make_context()

    asyncio.run(bot.cmd_unknown(update, context))

    update.message.reply_text.assert_called_once_with(messages.HELP_TEXT)


# ---------------------------------------------------------------------------
# Concrete non-reply preservation cases
# ---------------------------------------------------------------------------

def test_non_reply_plain_text_receives_help_text():
    """Concrete case (Req 3.1): non-reply plain text "hello" → one HELP_TEXT.

    EXPECTED TO PASS on unfixed code.
    """
    update = make_non_reply_update("hello")
    context = make_context()

    asyncio.run(bot.cmd_unknown(update, context))

    update.message.reply_text.assert_called_once_with(messages.HELP_TEXT)


def test_non_reply_unknown_command_receives_help_text():
    """Concrete case (Req 3.2): non-reply unknown command "/foo" → one HELP_TEXT.

    EXPECTED TO PASS on unfixed code.
    """
    update = make_non_reply_update("/foo")
    context = make_context()

    asyncio.run(bot.cmd_unknown(update, context))

    update.message.reply_text.assert_called_once_with(messages.HELP_TEXT)

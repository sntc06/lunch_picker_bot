"""bot.py — Telegram command handlers for the Lunch Bot."""

import logging
import random
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
import messages
import storage

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

REMOVEALL_YES_DATA = "removeall:yes"
REMOVEALL_NO_DATA = "removeall:no"


def select_roll(restaurants: list[dict], previous: str | None, no_repeat: bool) -> dict:
    """Pure helper that selects one restaurant entry from *restaurants*.

    This contains the no-repeat-aware selection logic for ``/roll`` with no
    Telegram or storage I/O, so it can be property-tested directly.

    Args:
        restaurants: non-empty list of restaurant dicts (each with ``name``,
            ``added_by``, ``added_at``). Not mutated.
        previous: the chat's ``Previous_Roll_Result`` — a lowercase name
            string (as stored by ``storage.save_previous_roll``) or ``None``.
        no_repeat: the ``No_Repeat_Toggle`` value.

    Returns:
        A single restaurant entry (dict) drawn from *restaurants*.

    Selection rules (Req 3.1, 3.3, 3a.3–3a.7):
      - ``no_repeat`` disabled → choose uniformly from the entire list.
      - ``no_repeat`` enabled:
          * single-restaurant list → return that restaurant (Req 3a.4);
          * ``previous`` is ``None`` or not present in the list → choose
            uniformly from the entire list (Req 3a.5, 3a.6);
          * otherwise → choose uniformly from the list excluding the entry
            whose name equals ``previous`` (case-insensitive) (Req 3a.3).

    The candidate list is built exactly once and ``random.choice`` is called
    exactly once — no rejection-sampling loop — guaranteeing bounded
    selection (Req 3a.11).
    """
    if no_repeat:
        # Exclude the previous result (compared case-insensitively, since
        # `previous` is already lowercase). If nothing remains — e.g. a
        # single-restaurant list, or `previous` is None/not present — fall
        # back to the full list so the candidate set is never empty.
        candidates = [
            entry for entry in restaurants if entry["name"].lower() != previous
        ]
        if not candidates:
            candidates = restaurants
    else:
        candidates = restaurants

    return random.choice(candidates)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /add <name1> [name2 ...] — multi-name with validation."""
    chat_id = update.effective_chat.id
    args = context.args

    if not args:
        await update.message.reply_text(messages.ADD_USAGE)
        return

    user = update.effective_user
    added_by = user.username or user.first_name
    reply_lines = []

    try:
        restaurants = storage.load(chat_id)
        changed = False

        for name in args:
            # Reject names containing newline or forward slash
            if "\n" in name or "/" in name:
                reply_lines.append(messages.ADD_INVALID_NAME.format(name=name))
                continue

            # Case-insensitive duplicate check
            if any(entry["name"].lower() == name.lower() for entry in restaurants):
                reply_lines.append(messages.ADD_DUPLICATE.format(name=name))
                continue

            added_at = datetime.now(TZ_TAIPEI).isoformat()
            restaurants.append({"name": name, "added_by": added_by, "added_at": added_at})
            reply_lines.append(messages.ADD_SUCCESS.format(name=name))
            changed = True

        if changed:
            storage.save(chat_id, restaurants)

        await update.message.reply_text("\n".join(reply_lines))
    except Exception:
        logger.exception("Storage error in cmd_add for chat %s", chat_id)
        await update.message.reply_text(messages.STORAGE_ERROR)



async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /remove <restaurant_name>."""
    chat_id = update.effective_chat.id
    args = context.args

    if not args:
        await update.message.reply_text(messages.REMOVE_USAGE)
        return

    name = " ".join(args).strip()

    try:
        restaurants = storage.load(chat_id)
        for entry in restaurants:
            if entry["name"].lower() == name.lower():
                restaurants.remove(entry)
                storage.save(chat_id, restaurants)
                await update.message.reply_text(messages.REMOVE_SUCCESS.format(name=name))
                return

        await update.message.reply_text(messages.REMOVE_NOT_FOUND.format(name=name))
    except Exception:
        logger.exception("Storage error in cmd_remove for chat %s", chat_id)
        await update.message.reply_text(messages.STORAGE_ERROR)


async def cmd_removeall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /removeall — ask for confirmation via inline keyboard."""
    chat_id = update.effective_chat.id

    try:
        restaurants = storage.load(chat_id)
        if not restaurants:
            await update.message.reply_text(messages.REMOVEALL_EMPTY)
            return

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(messages.REMOVEALL_YES, callback_data=REMOVEALL_YES_DATA),
                InlineKeyboardButton(messages.REMOVEALL_NO, callback_data=REMOVEALL_NO_DATA),
            ]
        ])
        await update.message.reply_text(messages.REMOVEALL_CONFIRM, reply_markup=keyboard)
    except Exception:
        logger.exception("Storage error in cmd_removeall for chat %s", chat_id)
        await update.message.reply_text(messages.STORAGE_ERROR)


async def callback_removeall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard callbacks for /removeall confirmation."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    if query.data == REMOVEALL_YES_DATA:
        try:
            storage.save(chat_id, [])
            await query.edit_message_text(messages.REMOVEALL_SUCCESS)
        except Exception:
            logger.exception("Storage error in callback_removeall for chat %s", chat_id)
            await query.edit_message_text(messages.STORAGE_ERROR)
    else:
        await query.edit_message_text(messages.REMOVEALL_CANCEL)


async def cmd_roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /roll — pick a random restaurant, avoiding the previous result."""
    chat_id = update.effective_chat.id

    # Read operations (load, load_previous_roll) fall into the STORAGE_ERROR
    # path if they fail.
    try:
        restaurants = storage.load(chat_id)
        if not restaurants:
            await update.message.reply_text(messages.ROLL_EMPTY)
            return

        previous = storage.load_previous_roll(chat_id)
    except Exception:
        logger.exception("Storage read error in cmd_roll for chat %s", chat_id)
        await update.message.reply_text(messages.STORAGE_ERROR)
        return

    # Toggle is read from config.NO_REPEAT only (constant for the run).
    pick = select_roll(restaurants, previous, config.NO_REPEAT)

    # Persist the result as the new Previous_Roll_Result. A persistence
    # failure here is logged but must NOT block returning the pick — the
    # worst case is that the next roll may repeat.
    try:
        storage.save_previous_roll(chat_id, pick["name"])
    except Exception:
        logger.exception(
            "Failed to persist previous roll for chat %s", chat_id
        )

    await update.message.reply_text(messages.ROLL_RESULT.format(name=pick["name"]))


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /list — show all restaurants."""
    chat_id = update.effective_chat.id

    try:
        restaurants = storage.load(chat_id)
        if not restaurants:
            await update.message.reply_text(messages.LIST_EMPTY)
            return

        lines = []
        for i, entry in enumerate(restaurants, start=1):
            # Parse stored ISO 8601 timestamp and display in Asia/Taipei timezone
            added_at_dt = datetime.fromisoformat(entry["added_at"]).astimezone(TZ_TAIPEI)
            added_at_str = added_at_dt.strftime("%Y-%m-%d %H:%M")
            lines.append(
                messages.LIST_ITEM.format(
                    index=i,
                    name=entry["name"],
                    added_by=entry["added_by"],
                    added_at=added_at_str,
                )
            )

        await update.message.reply_text(
            messages.LIST_HEADER.format(items="\n".join(lines))
        )
    except Exception:
        logger.exception("Storage error in cmd_list for chat %s", chat_id)
        await update.message.reply_text(messages.STORAGE_ERROR)


async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any unrecognised command or plain text."""
    await update.message.reply_text(messages.HELP_TEXT)

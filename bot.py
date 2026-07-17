"""bot.py — Telegram command handlers for the Lunch Bot."""

import logging
import random
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes

import config
import messages
import storage

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

REMOVEALL_YES_DATA = "removeall:yes"
REMOVEALL_NO_DATA = "removeall:no"


def select_roll(
    restaurants: list[dict], recent_history: list[str], no_repeat_window: int
) -> dict:
    """Pure helper that selects one restaurant entry from *restaurants*.

    This contains the No_Repeat_Window-aware selection logic for ``/roll``
    with no Telegram or storage I/O, so it can be property-tested directly.

    Args:
        restaurants: non-empty list of restaurant dicts (each with ``name``,
            ``added_by``, ``added_at``). Not mutated.
        recent_history: the chat's ``Recent_Roll_History`` — an ordered list
            of lowercase result names, most recent last (as stored by
            ``storage``). Not mutated.
        no_repeat_window: the ``No_Repeat_Window`` value (>= 0).

    Returns:
        A single restaurant entry (dict) drawn from *restaurants*.

    Selection rules (Req 3.1, 3.3, 3a.5–3a.11, 3a.15):
      - ``no_repeat_window == 0`` → choose uniformly from the entire list
        (Req 3a.5).
      - ``no_repeat_window >= 1``:
          * single-restaurant list → return that restaurant (Req 3a.9);
          * effective window = the most recent
            ``min(no_repeat_window, len(recent_history))`` history entries;
            if empty (no history recorded) → choose uniformly from the
            entire list (Req 3a.10);
          * build the excluded-name set from the effective-window entries,
            compared case-insensitively, ignoring any window name not
            currently present in the list (Req 3a.11);
          * ``Eligible_Restaurants`` = entries not in the excluded set;
            while it is empty, drop the oldest excluded name (relaxing
            oldest → newest) and recompute (Req 3a.7);
          * choose uniformly from ``Eligible_Restaurants`` (Req 3a.6, 3a.8).

    The candidate list is built at most once per relaxation step (at most
    ``1 + window`` steps total, since each step permanently drops one
    excluded name) and ``random.choice`` is called exactly once — no
    rejection-sampling loop — guaranteeing bounded selection (Req 3a.15).
    """
    # Window 0 disables the behaviour entirely (Req 3a.5).
    if no_repeat_window == 0:
        return random.choice(restaurants)

    # Single-restaurant list: that restaurant is always the result (Req 3a.9).
    if len(restaurants) == 1:
        return restaurants[0]

    # Effective window = the most recent min(window, len(history)) entries,
    # oldest first (Req 3a.6). Empty history → no exclusion (Req 3a.10).
    effective = min(no_repeat_window, len(recent_history))
    window_names = recent_history[len(recent_history) - effective:]
    if not window_names:
        return random.choice(restaurants)

    # Excluded names, ordered oldest → newest, compared case-insensitively.
    # Window names not currently present in the list exclude nothing and are
    # dropped up front (Req 3a.11).
    present_names = {entry["name"].lower() for entry in restaurants}
    excluded = [n.lower() for n in window_names if n.lower() in present_names]

    # Graceful relaxation (Req 3a.7): if excluding everything in `excluded`
    # leaves no eligible restaurant, drop the oldest excluded name and
    # recompute. `drop` only ever increases, so this terminates in at most
    # len(excluded) <= window relaxation steps (Req 3a.15); once `drop`
    # reaches len(excluded) the eligible set is the whole (non-empty) list.
    drop = 0
    while True:
        excluded_set = set(excluded[drop:])
        eligible = [
            entry
            for entry in restaurants
            if entry["name"].lower() not in excluded_set
        ]
        if eligible:
            return random.choice(eligible)
        drop += 1


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
    """Handle /roll — pick a random restaurant, avoiding recent results.

    Uses the No_Repeat_Window-aware selection logic: the chat's
    Recent_Roll_History is loaded and passed to ``select_roll`` together with
    ``config.NO_REPEAT_WINDOW`` so the most recent results (within the window)
    are avoided when possible.
    """
    chat_id = update.effective_chat.id

    # Read operations (load, load_recent_rolls) fall into the STORAGE_ERROR
    # path if they fail.
    try:
        restaurants = storage.load(chat_id)
        if not restaurants:
            await update.message.reply_text(messages.ROLL_EMPTY)
            return

        recent_history = storage.load_recent_rolls(chat_id)
    except Exception:
        logger.exception("Storage read error in cmd_roll for chat %s", chat_id)
        await update.message.reply_text(messages.STORAGE_ERROR)
        return

    # Window is read from config.NO_REPEAT_WINDOW only (constant for the run).
    pick = select_roll(restaurants, recent_history, config.NO_REPEAT_WINDOW)

    # Append and persist the result to the Recent_Roll_History. A persistence
    # failure inside append_recent_roll is logged there and does NOT raise —
    # the in-memory history is returned instead — so the pick is always
    # delivered regardless of persistence success (Req 3a.16).
    storage.append_recent_roll(chat_id, pick["name"], config.NO_REPEAT_WINDOW)

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
    """Handle any unrecognised command or plain text (ignore replies)."""
    if update.message.reply_to_message is not None:
        return
    await update.message.reply_text(messages.HELP_TEXT)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler registered via ``Application.add_error_handler``.

    Without a registered handler, python-telegram-bot logs every uncaught error
    (including the transient ``NetworkError``/``TimedOut`` raised while polling
    ``getUpdates``) with a full multi-frame traceback. Those network blips are
    common and self-recovering, so they flood the journal with noise.

    Registering this handler suppresses that default behaviour. Transient
    network errors are condensed to a single concise WARNING line; any other
    (unexpected) error is still logged with a full traceback so real bugs stay
    debuggable.

    When ``LOG_LEVEL=DEBUG``, the full stack trace is included for transient
    network errors too, so the original tracebacks remain available when
    actively debugging.
    """
    err = context.error
    if isinstance(err, (NetworkError, TimedOut)):
        # Attach the traceback only at DEBUG so normal WARNING-level logs stay
        # to a single concise line.
        debug = logger.isEnabledFor(logging.DEBUG)
        logger.warning(
            "Transient network error while polling: %s",
            err,
            exc_info=err if debug else None,
        )
        return
    logger.error("Unhandled error: %s", err, exc_info=err)

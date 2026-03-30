"""bot.py — Telegram command handlers for the Lunch Bot."""

import logging
import random
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import messages
import storage

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))
MAX_RESTAURANTS = 20

REMOVEALL_YES_DATA = "removeall:yes"
REMOVEALL_NO_DATA = "removeall:no"


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

            # Check list capacity
            if len(restaurants) >= MAX_RESTAURANTS:
                reply_lines.append(messages.ADD_LIST_FULL.format(name=name))
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
    """Handle /roll — pick a random restaurant."""
    chat_id = update.effective_chat.id

    try:
        restaurants = storage.load(chat_id)
        if not restaurants:
            await update.message.reply_text(messages.ROLL_EMPTY)
            return

        pick = random.choice(restaurants)
        await update.message.reply_text(messages.ROLL_RESULT.format(name=pick["name"]))
    except Exception:
        logger.exception("Storage error in cmd_roll for chat %s", chat_id)
        await update.message.reply_text(messages.STORAGE_ERROR)


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

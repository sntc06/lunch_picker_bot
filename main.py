"""main.py — Entry point for the Telegram Lunch Bot.

Wires config → storage → bot handlers → ``Application.run_polling()``.

Logging is sent to stdout so that, when the bot runs under systemd, the
output is captured by journald and is viewable with ``journalctl -u
lunch-bot`` (Req 8.4). Importing ``config`` at startup also triggers the
``BOT_TOKEN`` validation, so a missing token fails fast before any network
call (Req 8.5).

The ``/roll`` no-repeat behaviour survives restarts automatically: the
previous roll result is persisted per chat to disk and re-read on each
``/roll`` via ``storage.load_previous_roll`` (Req 3a.9), so no in-memory
startup load is required.
"""

import json
import logging
import sys

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

import config
import bot
import storage

# Direct logs to stdout (not the default stderr) so systemd/journald captures
# operational output (Req 8.4). The level is read from config.LOG_LEVEL
# (env / .env, default WARNING) — WARNING suppresses httpx's per-request INFO
# lines (one per getUpdates/sendMessage poll) while the handlers'
# logger.exception calls (ERROR level) are always recorded. Set LOG_LEVEL=INFO
# or DEBUG to get more detail when debugging.
logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def load_all_recent_rolls() -> dict[str, list[str]]:
    """Load every chat's persisted ``Recent_Roll_History`` at startup.

    Reading the history at startup means recent-repeat avoidance applies again
    after a restart (Req 3a.13). The per-chat load goes through
    ``storage.load_recent_rolls``, which treats an unreadable/unparseable entry
    as empty (``[]``) and logs the failure (Req 3a.17). A missing history file
    simply yields no chats to load, and a wholly unparseable file is likewise
    treated as "no recorded history" with the failure logged, so startup always
    proceeds.

    Returns a mapping of ``chat_id`` (str) → ordered history (most recent last).
    """
    # Enumerate chats from the same file binding storage's per-chat loader
    # reads, so the two never diverge (both are read from config at import).
    recent_rolls_file = storage.RECENT_ROLLS_FILE
    try:
        with open(recent_rolls_file, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        # No history persisted yet — nothing to warm up.
        return {}
    except (OSError, ValueError) as exc:
        logger.error(
            "Failed to read recent-roll history from %s at startup; "
            "treating all history as empty: %s",
            recent_rolls_file,
            exc,
        )
        return {}

    if not isinstance(data, dict):
        logger.error(
            "Recent-roll history in %s is not a JSON object at startup; "
            "treating all history as empty.",
            recent_rolls_file,
        )
        return {}

    # Delegate per-chat parsing to storage.load_recent_rolls so a corrupt
    # per-chat entry is treated as empty and logged (Req 3a.17) while the
    # remaining chats still load.
    histories = {
        str(chat_id): storage.load_recent_rolls(chat_id) for chat_id in data
    }
    logger.info(
        "Loaded recent-roll history for %d chat(s) at startup.", len(histories)
    )
    return histories


if __name__ == "__main__":
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # Load each chat's persisted Recent_Roll_History so recent-repeat avoidance
    # applies after a restart; unreadable histories are treated as empty and
    # logged (Req 3a.13, 3a.17). Stash it on the Application so it is available
    # to the process (each /roll still reads the durable on-disk history).
    app.bot_data["recent_roll_history"] = load_all_recent_rolls()

    app.add_handler(CommandHandler("add", bot.cmd_add))
    app.add_handler(CommandHandler("remove", bot.cmd_remove))
    app.add_handler(CommandHandler("removeall", bot.cmd_removeall))
    app.add_handler(CallbackQueryHandler(bot.callback_removeall, pattern="^removeall:"))
    app.add_handler(CommandHandler("roll", bot.cmd_roll))
    app.add_handler(CommandHandler("list", bot.cmd_list))
    app.add_handler(MessageHandler(filters.COMMAND, bot.cmd_unknown))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.cmd_unknown))

    # Collapse noisy transient-network tracebacks into a single concise line.
    app.add_error_handler(bot.error_handler)

    app.run_polling()

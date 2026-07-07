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

import logging
import sys

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

import config
import bot

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

if __name__ == "__main__":
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

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

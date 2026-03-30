"""main.py — Entry point for the Telegram Lunch Bot."""

import logging

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

import config
import bot

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
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

    app.run_polling()

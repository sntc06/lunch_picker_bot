# Telegram Lunch Bot

A Telegram bot that helps you decide where to eat lunch. Maintain a list of restaurants per chat and roll one at random.

## Commands

- `/add <餐廳名稱>` — add a restaurant
- `/remove <餐廳名稱>` — remove a restaurant
- `/list` — show all restaurants
- `/roll` — pick one at random

## Setup

### 1. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure `.env`

Create a `.env` file in the project root:

```env
# Required: your Telegram bot token from @BotFather
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz

# Optional: path to the JSON storage file (default: data/restaurants.json)
DATA_FILE=data/restaurants.json
```

### 3. Run the bot

```bash
python main.py
```

## Deployment (systemd)

Copy the service file and enable it:

```bash
sudo cp deploy/lunch-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lunch-bot
sudo systemctl start lunch-bot
```

Logs: `journalctl -u lunch-bot -f`

The service expects the project to be installed at `/opt/lunch-bot` with a virtualenv at `/opt/lunch-bot/venv` and secrets in `/opt/lunch-bot/.env`.

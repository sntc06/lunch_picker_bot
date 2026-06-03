# Telegram Lunch Bot

A Telegram bot that helps you decide where to eat lunch. Maintain a list of restaurants per chat and roll one at random.

## Commands

- `/add <餐廳名稱> [餐廳名稱2 ...]` — add one or more restaurants
- `/remove <餐廳名稱>` — remove a restaurant
- `/removeall` — clear the entire list (asks for confirmation)
- `/list` — show all restaurants
- `/roll` — pick one at random

### No-repeat rolls

By default, `/roll` avoids returning the same restaurant on two successive rolls in the same chat, so repeated rolls feel more varied. The most recent result is remembered per chat on disk, so this behavior keeps working after a restart. It degrades gracefully when avoiding a repeat isn't possible (for example, a single-restaurant list). You can turn it off with the `NO_REPEAT` setting (see below).

## Setup

### 1. Create a virtual environment and install dependencies

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run project commands through the venv executables directly (no shell activation needed):

```bash
.venv/bin/python main.py
.venv/bin/pytest
```

To install the development/test dependencies as well:

```bash
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

### 2. Configure `.env`

Create a `.env` file in the project root:

```env
# Required: your Telegram bot token from @BotFather
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz

# Optional: path to the JSON storage file (default: data/restaurants.json)
DATA_FILE=data/restaurants.json

# Optional: path to the previous-roll JSON file used for no-repeat rolls
# (default: previous_roll.json beside DATA_FILE)
PREVIOUS_ROLL_FILE=data/previous_roll.json

# Optional: avoid repeating the previous /roll result in the same chat.
# Enabled by default. Accepts 1/true/yes/on (enabled) or 0/false/no/off
# (disabled), case-insensitive. Unrecognized values fall back to enabled.
NO_REPEAT=true
```

### 3. Run the bot

```bash
.venv/bin/python main.py
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

The service expects the project to be installed at `/opt/lunch-bot` with a virtualenv at `/opt/lunch-bot/venv` and secrets in `/opt/lunch-bot/.env`. To create the virtualenv on the server:

```bash
cd /opt/lunch-bot
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

The service runs the bot via `/opt/lunch-bot/venv/bin/python main.py`, and any optional settings (`DATA_FILE`, `PREVIOUS_ROLL_FILE`, `NO_REPEAT`) can be set in `/opt/lunch-bot/.env`.

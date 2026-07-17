# Telegram Lunch Bot

A Telegram bot that helps you decide where to eat lunch. Maintain a list of restaurants per chat and roll one at random.

## Commands

- `/add <餐廳名稱> [餐廳名稱2 ...]` — add one or more restaurants
- `/remove <餐廳名稱>` — remove a restaurant
- `/removeall` — clear the entire list (asks for confirmation)
- `/list` — show all restaurants
- `/roll` — pick one at random

### No-repeat rolls

By default, `/roll` avoids returning any restaurant selected too recently in the same chat, so repeated rolls feel more varied. This is controlled by `NO_REPEAT_WINDOW`, an integer count of the most recent results to exclude:

- `0` — disabled; every roll picks from the entire list.
- `1` (default) — excludes only the single most recent result.
- `N` (up to 1000) — excludes up to the `N` most recent results.

Each chat's recent-roll history is remembered per chat on disk, so this behavior keeps working after a restart. It degrades gracefully — relaxing the exclusion oldest-first — when excluding the recent window would otherwise leave no restaurant to pick (for example, a single-restaurant list, or a list smaller than the window).

For backward compatibility with the earlier on/off setting, a truthy value (`true`/`yes`/`on`) is treated as `1` and a falsy value (`false`/`no`/`off`) as `0`. Any value that isn't a valid integer in range `0`–`1000` or a recognized boolean falls back to the default of `1`.

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

# Optional: path to the recent-roll-history JSON file used for no-repeat rolls
# (default: recent_rolls.json beside DATA_FILE)
RECENT_ROLLS_FILE=data/recent_rolls.json

# Optional: number of most recent /roll results to avoid repeating in the
# same chat. Integer 0-1000 (default: 1). 0 disables the behavior. For
# backward compatibility, 1/true/yes/on maps to 1 and 0/false/no/off maps
# to 0, case-insensitive. Unrecognized values fall back to the default (1).
NO_REPEAT_WINDOW=1

# Optional: logging verbosity (default: WARNING). One of
# CRITICAL/ERROR/WARNING/INFO/DEBUG, case-insensitive. WARNING keeps the
# journal quiet by suppressing per-request HTTP logs; use INFO or DEBUG
# for more detail when troubleshooting. Unrecognized values fall back to
# WARNING.
LOG_LEVEL=WARNING
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

The service runs the bot via `/opt/lunch-bot/venv/bin/python main.py`, and any optional settings (`DATA_FILE`, `RECENT_ROLLS_FILE`, `NO_REPEAT_WINDOW`, `LOG_LEVEL`) can be set in `/opt/lunch-bot/.env`.

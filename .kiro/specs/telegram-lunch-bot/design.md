# Design Document

## Overview

The Telegram Lunch Bot is a single-process Python application that connects to the Telegram Bot API via long-polling. It maintains a per-chat restaurant list in a local JSON file and responds to five slash commands: `/add`, `/remove`, `/removeall`, `/roll`, and `/list`. The bot runs as a systemd service on an Ubuntu Linux server with no GUI requirement.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  lunch_bot/                      │
│                                                  │
│  main.py          ← entry point, wires up bot   │
│  bot.py           ← command handlers            │
│  storage.py       ← JSON persistence layer      │
│  config.py        ← reads env / config file     │
│  messages.py      ← all zh-TW response strings  │
└─────────────────────────────────────────────────┘

External:
  Telegram Bot API  ← long-polling via python-telegram-bot
  data/restaurants.json  ← persistent storage file
  /etc/systemd/system/lunch-bot.service  ← systemd unit
```

The design is intentionally flat — no database, no web framework, no async complexity beyond what python-telegram-bot provides out of the box.

All user-facing response strings are written in Traditional Chinese as used in Taiwan (zh-TW, 繁體中文). Simplified Chinese (zh-CN) is not used. All message strings are centralised in a single `messages.py` module so they can be reviewed and updated in one place.

## Components

### messages.py

Central module holding every user-facing string in Traditional Chinese (zh-TW). `bot.py` imports constants from here — no string literals appear in handler code.

```python
# Example constants (Traditional Chinese, Taiwan conventions)
ADD_SUCCESS       = "✅ 已新增餐廳：{name}"
ADD_DUPLICATE     = "⚠️ 「{name}」已在清單中了。"
ADD_USAGE         = "用法：/add <餐廳名稱> [餐廳名稱2 ...]"
ADD_INVALID_NAME  = "⚠️ 餐廳名稱格式不正確，名稱不可包含換行或斜線：{name}"
REMOVE_SUCCESS    = "✅ 已移除餐廳：{name}"
REMOVE_NOT_FOUND  = "⚠️ 找不到「{name}」，請確認名稱是否正確。"
REMOVE_USAGE      = "用法：/remove <餐廳名稱>"
REMOVEALL_CONFIRM = "⚠️ 確定要清空整個餐廳清單嗎？"
REMOVEALL_YES     = "是，清空"
REMOVEALL_NO      = "否，取消"
REMOVEALL_SUCCESS = "✅ 已清空餐廳清單。"
REMOVEALL_CANCEL  = "已取消，清單保持不變。"
REMOVEALL_EMPTY   = "清單已經是空的了。"
ROLL_RESULT       = "🎲 今天去吃：{name}"
ROLL_EMPTY        = "清單是空的，請先用 /add 新增餐廳。"
LIST_HEADER       = "📋 目前的餐廳清單：\n{items}"
LIST_ITEM         = "{index}. {name}（由 {added_by} 於 {added_at} 新增）"
LIST_EMPTY        = "清單是空的，請先用 /add 新增餐廳。"
STORAGE_ERROR     = "⚠️ 操作失敗，請稍後再試。"
HELP_TEXT         = (
    "可用指令：\n"
    "/add <餐廳名稱> [餐廳名稱2 ...] — 新增一或多間餐廳\n"
    "/remove <餐廳名稱> — 移除餐廳\n"
    "/removeall — 清空整個清單\n"
    "/list — 查看清單\n"
    "/roll — 隨機選一間"
)
```

### config.py

Reads the bot token and data file path from environment variables or a `.env` file. Raises a clear error at startup if required values are missing.

```
BOT_TOKEN   — Telegram bot token (required)
DATA_FILE   — path to JSON storage file (default: data/restaurants.json)
```

### storage.py

Thin wrapper around a JSON file. Keyed by `chat_id` so each chat has its own list.

```python
load(chat_id) -> list[dict]
save(chat_id, restaurants: list[dict]) -> None
```

- Reads/writes atomically (write to temp file, then rename) to avoid corruption on crash.
- All names stored lowercase for case-insensitive deduplication.

### bot.py

Contains one handler per command. Each handler calls storage, applies business logic, and replies.

| Handler | Trigger | Logic |
|---|---|---|
| `cmd_add` | `/add <name> [name2 ...]` | split args into names → for each: validate (reject if contains `\n` or `/`) → check list-full (max 20) → check duplicate → append entry → save → reply with per-name summary |
| `cmd_remove` | `/remove <name>` | load list → find entry by name (case-insensitive) → remove → save → reply |
| `cmd_removeall` | `/removeall` | load list → guard empty → send confirmation message with Yes/No inline keyboard → on confirm: clear list, save, reply success; on cancel: reply cancelled |
| `cmd_roll` | `/roll` | load list → guard empty → `random.choice` → reply with `entry["name"]` |
| `cmd_list` | `/list` | load list → guard empty → format numbered list with name, added_by, added_at → reply |
| `cmd_unknown` | any other message | reply with help text |

**Name validation rules (applied in `cmd_add`):**
- A name is invalid if it contains `\n` (newline) or `/` (forward slash).
- Invalid names are rejected immediately with `ADD_INVALID_NAME`; valid names in the same batch continue to be processed.

**`/add` multi-name behaviour:**
- Arguments are split on whitespace; each token is treated as a separate restaurant name.
- The reply summarises all outcomes (added, duplicate, invalid, list-full) in one message.

### main.py

Wires config → storage → bot handlers → `Application.run_polling()`. Logging is configured to stdout so systemd/journald captures it automatically.

## Data Model

```json
{
  "123456789": [
    {"name": "pizza palace", "added_by": "alice", "added_at": "2026-03-30T12:00:00+08:00"},
    {"name": "sushi spot",   "added_by": "bob",   "added_at": "2026-03-30T13:30:00+08:00"}
  ],
  "987654321": [
    {"name": "burger barn",  "added_by": "carol",  "added_at": "2026-03-29T09:00:00+08:00"}
  ]
}
```

- File location: configurable via `DATA_FILE` env var.
- `name` is always stored lowercase for case-insensitive deduplication.
- `added_by` is `update.effective_user.username` with `first_name` as fallback.
- `added_at` is stored as an ISO 8601 timestamp with `+08:00` offset (Asia/Taipei) and displayed in Taiwan local time.

## Deployment: systemd Service

A unit file is provided at `deploy/lunch-bot.service`:

```ini
[Unit]
Description=Telegram Lunch Bot
After=network.target

[Service]
Type=simple
User=lunchbot
WorkingDirectory=/opt/lunch-bot
EnvironmentFile=/opt/lunch-bot/.env
ExecStart=/opt/lunch-bot/venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Setup steps (CLI only):

```bash
sudo cp deploy/lunch-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lunch-bot
sudo systemctl start lunch-bot
```

Logs via: `journalctl -u lunch-bot -f`

## Correctness Properties

### Property 1: Case-insensitive deduplication (Req 1.5)

For any restaurant name `n`, adding `n` and then adding any case variant of `n` must result in a rejection. The list must contain exactly one entry.

```
∀ name n: add(n) → add(n.upper()) → list contains n exactly once
```

### Property 2: Round-trip persistence (Req 4.1, 5.1, 5.2)

For any sequence of add/remove operations, saving and reloading the storage must produce an equivalent list of dicts with identical `name`, `added_by`, and `added_at` fields.

```
∀ list[dict] L: save(chat_id, L) → load(chat_id) == L
```

### Property 3: Uniform random selection (Req 3.3)

Over a large number of rolls on a list of `k` restaurants, each restaurant should appear with frequency approximately `1/k`. Verified statistically (chi-squared or frequency count within tolerance).

### Property 4: Roll result is always from the list (Req 3.1)

```
∀ non-empty list L: roll(L) ∈ L
```

### Property 5: Config missing token fails fast (Req 8.5)

When `BOT_TOKEN` is not set, the application must raise a clear error before attempting any network connection.

### Property 6: Invalid name rejection (Req 1.6)

For any name containing `\n` or `/`, `cmd_add` must reject it and never append it to the list.

```
∀ name n where '\n' ∈ n or '/' ∈ n: add(n) → list unchanged, reply ADD_INVALID_NAME
```

## Error Handling

All reply strings are in Traditional Chinese (zh-TW) sourced from `messages.py`.

| Situation | Behavior |
|---|---|
| Storage read fails | Log error, reply「⚠️ 操作失敗，請稍後再試。」 |
| Storage write fails | Log error, reply「⚠️ 操作失敗，請稍後再試。」 |
| `/add` with no argument | Reply with usage:「用法：/add <餐廳名稱> [餐廳名稱2 ...]」 |
| `/add` name contains `\n` or `/` | Reply with「⚠️ 餐廳名稱格式不正確，名稱不可包含換行或斜線：{name}」 |
| `/remove` with no argument | Reply with usage:「用法：/remove <餐廳名稱>」 |
| `/removeall` on empty list | Reply「清單已經是空的了。」 |
| `/removeall` — user cancels confirmation | Reply「已取消，清單保持不變。」 |
| Unknown command or plain text | Reply with help listing all five commands (zh-TW) |
| Missing `BOT_TOKEN` at startup | Raise `RuntimeError` with descriptive message, exit non-zero |

## Dependencies

```
python-telegram-bot>=20.0
python-dotenv>=1.0
```

Python 3.10+ (available on Ubuntu 22.04 LTS and later).

No GUI libraries. No database. No external services beyond the Telegram Bot API.

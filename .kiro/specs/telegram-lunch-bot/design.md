# Design Document

## Overview

The Telegram Lunch Bot is a single-process Python application that connects to the Telegram Bot API via long-polling. It maintains a per-chat restaurant list in a local JSON file and responds to five slash commands: `/add`, `/remove`, `/removeall`, `/roll`, and `/list`. The bot runs as a systemd service on an Ubuntu Linux server with no GUI requirement.

To make repeated rolls feel useful, `/roll` supports a "no-repeat" behavior that avoids returning the same restaurant on two successive rolls in the same chat. This is governed by the `No_Repeat_Toggle`, a persistent configuration setting (default: enabled) read from the environment / `.env` file at startup — the same mechanism used for the bot token and data file path — and constant for the duration of a run. To support this, the bot remembers each chat's most recent roll result (the `Previous_Roll_Result`) on disk in the data folder so the behavior survives restarts, and degrades gracefully when avoiding a repeat is impossible (for example, a single-restaurant list).

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
  data/restaurants.json   ← persistent restaurant lists
  data/previous_roll.json ← persistent per-chat previous roll results
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

Reads the bot token, data file path, and no-repeat toggle from environment variables or a `.env` file. Raises a clear error at startup if required values are missing.

```
BOT_TOKEN         — Telegram bot token (required)
DATA_FILE         — path to restaurant-list JSON file (default: data/restaurants.json)
PREVIOUS_ROLL_FILE — path to previous-roll JSON file
                     (optional, default: previous_roll.json beside DATA_FILE)
NO_REPEAT         — No_Repeat_Toggle: avoid repeating the previous roll result
                     (optional, default: enabled)
```

The previous-roll file lives in the same data folder as `DATA_FILE` (Req 5.3); by default it is `previous_roll.json` in `DATA_FILE`'s directory, and it can be overridden with `PREVIOUS_ROLL_FILE`.

`NO_REPEAT` is parsed into a boolean `NO_REPEAT` constant at startup using the same truthy/falsy convention as a typical env flag (e.g. `1/true/yes/on` → enabled, `0/false/no/off` → disabled, case-insensitive). When the variable is absent the value defaults to `True` (enabled). The value is read once at startup and is constant for the lifetime of the process — there is no runtime command to change it.

### storage.py

Thin wrapper around two JSON files, both in the data folder: `DATA_FILE` for restaurant lists and `PREVIOUS_ROLL_FILE` for per-chat previous roll results. Both are keyed by `chat_id`. Keeping the previous-roll data in its own file leaves the existing `restaurants.json` format untouched (no migration needed) while still satisfying the "same data folder / durable on disk" requirement (Req 5.3).

```python
load(chat_id) -> list[dict]            # restaurant list for a chat (DATA_FILE)
save(chat_id, restaurants: list[dict]) -> None

load_previous_roll(chat_id) -> str | None   # most recent roll result, or None (PREVIOUS_ROLL_FILE)
save_previous_roll(chat_id, name: str) -> None
```

- Both files are read/written atomically (write to temp file, then rename) to avoid corruption on crash, using the same helper used for the restaurant list.
- Restaurant names are stored lowercase for case-insensitive deduplication.
- `Previous_Roll_Result` is stored per chat in `PREVIOUS_ROLL_FILE` (Req 5.3), so it survives restarts (Req 3a.9) and is independent per chat (Req 3a.10).
- `load_previous_roll` returns `None` when the file is missing or the chat has no entry — i.e. no roll has ever produced a result for that chat (Req 3a.5).
- The previous roll result is stored using the same lowercase form as restaurant names so membership comparisons against the list are consistent.

### bot.py

Contains one handler per command. Each handler calls storage, applies business logic, and replies.

| Handler | Trigger | Logic |
|---|---|---|
| `cmd_add` | `/add <name> [name2 ...]` | split args into names → for each: validate (reject if contains `\n` or `/`) → check list-full (max 20) → check duplicate → append entry → save → reply with per-name summary |
| `cmd_remove` | `/remove <name>` | load list → find entry by name (case-insensitive) → remove → save → reply |
| `cmd_removeall` | `/removeall` | load list → guard empty → send confirmation message with Yes/No inline keyboard → on confirm: clear list, save, reply success; on cancel: reply cancelled |
| `cmd_roll` | `/roll` | load list → guard empty → select via no-repeat-aware logic (see below) → record + persist result as `Previous_Roll_Result` → reply with `entry["name"]` |
| `cmd_list` | `/list` | load list → guard empty → format numbered list with name, added_by, added_at → reply |
| `cmd_unknown` | any other message | reply with help text |

**Name validation rules (applied in `cmd_add`):**
- A name is invalid if it contains `\n` (newline) or `/` (forward slash).
- Invalid names are rejected immediately with `ADD_INVALID_NAME`; valid names in the same batch continue to be processed.

**`/add` multi-name behaviour:**
- Arguments are split on whitespace; each token is treated as a separate restaurant name.
- The reply summarises all outcomes (added, duplicate, invalid, list-full) in one message.

**`/roll` selection logic (no-repeat behaviour):**

`cmd_roll` loads the restaurant list and guards the empty case (Req 3.2). It then selects a result using the following bounded decision, which never retries indefinitely (Req 3a.11):

1. If `config.NO_REPEAT` is **disabled** → select uniformly at random from the entire list (Req 3a.7). This is the same behaviour as Req 3.1/3.3.
2. If `config.NO_REPEAT` is **enabled**:
   - If the list has exactly one restaurant → return that restaurant (Req 3a.4).
   - Load `Previous_Roll_Result` for the chat:
     - If it is `None` (no roll has ever produced a result) → select uniformly at random from the entire list (Req 3a.5).
     - If it is set but no longer present in the list → select uniformly at random from the entire list (Req 3a.6).
     - Otherwise → compute `Eligible_Restaurants` = list excluding the entry whose name equals `Previous_Roll_Result`, and select uniformly at random from `Eligible_Restaurants` (Req 3a.3).
3. After a result is chosen, record it as the new `Previous_Roll_Result` for the chat and persist it via `storage.save_previous_roll` (Req 3a.8), then reply with the name.

Selection is implemented by building the candidate list once and calling `random.choice` a single time — no rejection-sampling loop — which guarantees bounded selection (Req 3a.11). The toggle is read from `config.NO_REPEAT` only, so its value is constant for the run (Req 3a.2).

### main.py

Wires config → storage → bot handlers → `Application.run_polling()`. Logging is configured to stdout so systemd/journald captures it automatically.

## Data Model

Two JSON files, both in the data folder.

**`DATA_FILE` (e.g. `data/restaurants.json`)** — maps each `chat_id` to its restaurant list. This format is unchanged from previous versions.

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

**`PREVIOUS_ROLL_FILE` (e.g. `data/previous_roll.json`)** — maps each `chat_id` to the name of that chat's most recent roll result.

```json
{
  "123456789": "sushi spot",
  "987654321": "burger barn"
}
```

- File locations: `DATA_FILE` via its env var; `PREVIOUS_ROLL_FILE` defaults to `previous_roll.json` beside `DATA_FILE` and is overridable. Both live in the data folder (Req 5.3).
- `name` is always stored lowercase for case-insensitive deduplication.
- `added_by` is `update.effective_user.username` with `first_name` as fallback.
- `added_at` is stored as an ISO 8601 timestamp with `+08:00` offset (Asia/Taipei) and displayed in Taiwan local time.
- A `chat_id` in `PREVIOUS_ROLL_FILE` holds the lowercase name of the most recent roll result for that chat, or is absent when no roll has produced a result yet. It is tracked independently per chat (Req 3a.10).
- Because the previous-roll data is a separate file, existing `restaurants.json` files continue to work as-is with no migration; a missing `PREVIOUS_ROLL_FILE` is treated as "no previous results recorded."

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

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Case-insensitive deduplication (Req 1.5)

For any restaurant name `n`, adding `n` and then adding any case variant of `n` must result in a rejection. The list must contain exactly one entry.

```
∀ name n: add(n) → add(n.upper()) → list contains n exactly once
```

### Property 2: Round-trip persistence of the restaurant list (Req 4.1, 5.1, 5.2)

For any sequence of add/remove operations, saving and reloading the storage must produce an equivalent list of dicts with identical `name`, `added_by`, and `added_at` fields.

```
∀ list[dict] L: save(chat_id, L) → load(chat_id) == L
```

### Property 3: Uniform random selection (Req 3.3)

Over a large number of rolls on a list of `k` restaurants (with the No_Repeat_Toggle disabled, so the whole list is eligible), each restaurant should appear with frequency approximately `1/k`. Verified statistically (chi-squared or frequency count within tolerance).

### Property 4: Roll result is always from the list (Req 3.1)

For any non-empty list, the roll result is always a member of the list, regardless of toggle state or previous result.

```
∀ non-empty list L: roll(L) ∈ L
```

### Property 5: No-repeat avoids the previous result (Req 3a.3, 3a.4)

For any restaurant list and any recorded `Previous_Roll_Result` that is present in the list, when the No_Repeat_Toggle is enabled the roll result must not equal the `Previous_Roll_Result` — **unless** the list contains exactly one restaurant, in which case that single restaurant is returned (graceful degradation).

```
∀ list L, ∀ prev ∈ L, toggle enabled:
    if |L| >= 2 → roll(L, prev) ∈ L and roll(L, prev) != prev
    if |L| == 1 → roll(L, prev) == the single element of L
```

### Property 6: Full-list eligibility when no-repeat does not constrain (Req 3a.5, 3a.6, 3a.7)

For any non-empty list, when the no-repeat exclusion does not apply — that is, when the No_Repeat_Toggle is disabled, OR no `Previous_Roll_Result` is recorded, OR the recorded `Previous_Roll_Result` is no longer present in the list — every restaurant in the list is eligible and the result is selected uniformly from the entire list (no element, including any prior result, is excluded).

```
∀ non-empty list L, ∀ prev (prev = None ∨ prev ∉ L ∨ toggle disabled):
    roll(L, prev) ∈ L, and over many rolls every element of L is reachable
```

### Property 7: Previous-roll persistence round-trip (Req 3a.8, 3a.9, 5.3)

For any roll that produces a result, the result is recorded as the chat's `Previous_Roll_Result` and persisted to disk, such that a fresh read (simulating a restart) returns the same value.

```
∀ chat c, ∀ name n: save_previous_roll(c, n) → load_previous_roll(c) == n
```

### Property 8: Per-chat independence of the previous roll result (Req 3a.10)

For any two distinct chats, recording the `Previous_Roll_Result` for one chat must not change the `Previous_Roll_Result` of the other.

```
∀ chats c1 != c2, ∀ names n1, n2:
    save_previous_roll(c1, n1) → load_previous_roll(c2) is unchanged
```

### Property 9: Bounded selection (Req 3a.11)

For any non-empty list and any combination of toggle state and previous result, the candidate set used for selection is non-empty and the roll completes by returning exactly one element — selection never loops or retries indefinitely.

```
∀ non-empty list L, ∀ toggle, ∀ prev:
    candidates(L, toggle, prev) is non-empty ∧ roll returns exactly one element of L
```

### Property 10: No_Repeat_Toggle parsing and default (Req 3a.1)

For any configuration input string, the parsed `NO_REPEAT` value matches the truthy/falsy convention (`1/true/yes/on` → enabled, `0/false/no/off` → disabled, case-insensitive); when the variable is absent the value defaults to enabled.

```
∀ env string s: parse_no_repeat(s) == truthy(s)
parse_no_repeat(absent) == True
```

### Property 11: Invalid name rejection (Req 1.6)

For any name containing `\n` or `/`, `cmd_add` must reject it and never append it to the list.

```
∀ name n where '\n' ∈ n or '/' ∈ n: add(n) → list unchanged, reply ADD_INVALID_NAME
```

### Non-property checks

The following acceptance criteria are verified by example-based, smoke, or config-wiring tests rather than property-based tests:

- **Req 3a.2** (toggle read once at startup, constant for the run): smoke check that `cmd_roll` reads `config.NO_REPEAT` and there is no runtime mutation path.
- **Req 8.5** (missing `BOT_TOKEN` fails fast): example test — unset `BOT_TOKEN`, assert startup raises a clear error before any network call.

## Error Handling

All reply strings are in Traditional Chinese (zh-TW) sourced from `messages.py`.

| Situation | Behavior |
|---|---|
| Storage read fails | Log error, reply「⚠️ 操作失敗，請稍後再試。」 |
| Storage write fails | Log error, reply「⚠️ 操作失敗，請稍後再試。」 |
| Previous-roll persistence fails during `/roll` | Log error; the roll result is still replied to the user. Failing to persist the previous result must not block returning a pick (worst case: the next roll may repeat). |
| `/add` with no argument | Reply with usage:「用法：/add <餐廳名稱> [餐廳名稱2 ...]」 |
| `/add` name contains `\n` or `/` | Reply with「⚠️ 餐廳名稱格式不正確，名稱不可包含換行或斜線：{name}」 |
| `/remove` with no argument | Reply with usage:「用法：/remove <餐廳名稱>」 |
| `/removeall` on empty list | Reply「清單已經是空的了。」 |
| `/removeall` — user cancels confirmation | Reply「已取消，清單保持不變。」 |
| Unknown command or plain text | Reply with help listing all five commands (zh-TW) |
| Missing `BOT_TOKEN` at startup | Raise `RuntimeError` with descriptive message, exit non-zero |
| Invalid / unset `NO_REPEAT` value | Treat absent as enabled (default); unrecognised values fall back to the default rather than failing startup |

## Testing Strategy

A dual approach is used: example/edge-case unit tests for specific behaviours, and property-based tests for universal properties.

**Property-based testing:**
- Library: [Hypothesis](https://hypothesis.readthedocs.io/) (the standard choice for Python).
- Each property in the Correctness Properties section is implemented by a single property-based test running a minimum of 100 iterations.
- The roll selection logic should be factored into a pure helper (e.g. `select_roll(restaurants, previous, no_repeat) -> entry`) so Properties 4–6 and 9 can be tested without the Telegram I/O layer.
- Storage round-trip and per-chat independence (Properties 2, 7, 8) are tested against temporary `DATA_FILE` and `PREVIOUS_ROLL_FILE` paths.
- Each property test is tagged with a comment referencing its design property, e.g.
  `# Feature: telegram-lunch-bot, Property 5: No-repeat avoids the previous result`.

**Unit / example / smoke tests:**
- Req 3a.2 — smoke test that `cmd_roll` consults `config.NO_REPEAT` and no runtime path mutates it.
- Req 8.5 — example test that an unset `BOT_TOKEN` raises at startup before any network call.
- Edge cases for the no-repeat boundary: single-restaurant list (Req 3a.4), previous result absent (Req 3a.5), and previous result removed from the list (Req 3a.6).
- Missing `PREVIOUS_ROLL_FILE`: `load_previous_roll` returns `None` for any chat (treated as "no previous results recorded").

**Existing tests** (`tests/test_config.py`, `tests/test_storage.py`, `tests/test_restaurant_names.py`, `tests/test_invalid_name_rejection.py`) remain valid; the storage tests should be extended for the new `previous_roll` functions and the separate `PREVIOUS_ROLL_FILE`.

## Dependencies

```
python-telegram-bot>=20.0
python-dotenv>=1.0
```

Python 3.10+ (available on Ubuntu 22.04 LTS and later).

No GUI libraries. No database. No external services beyond the Telegram Bot API.

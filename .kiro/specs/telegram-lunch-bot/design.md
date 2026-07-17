# Design Document

## Overview

The Telegram Lunch Bot is a single-process Python application that connects to the Telegram Bot API via long-polling. It maintains a per-chat restaurant list in a local JSON file and responds to five slash commands: `/add`, `/remove`, `/removeall`, `/roll`, and `/list`. The bot runs as a systemd service on an Ubuntu Linux server with no GUI requirement.

To make repeated rolls feel useful, `/roll` supports a configurable "no-repeat" behavior that avoids returning restaurants selected too recently in the same chat. This is governed by the `No_Repeat_Window`, a persistent **integer** configuration setting read from the environment / `.env` file at startup — the same mechanism used for the bot token and data file path — and constant for the duration of a run. Its semantics:

- **`0`** — the behavior is disabled; every roll selects from the entire list.
- **`1`** — only the single most recent result is excluded (this is the previous block-once behavior).
- **`N`** (up to 1000) — up to the `N` most recent results are excluded.

To support this, the bot remembers each chat's bounded `Recent_Roll_History` (an ordered list of recent result names, most recent last) on disk in the data folder so the behavior survives restarts, and it degrades gracefully — relaxing the exclusion oldest-first — when excluding the recent window would otherwise leave no restaurant to pick (for example, when the list is small relative to the window).

For backward compatibility with earlier boolean-style configuration, a truthy value (`true`/`yes`/`on`) is interpreted as `1` and a falsy value (`false`/`no`/`off`) as `0`. Any value that cannot be interpreted as an integer in range `0`–`1000` or as a supported boolean falls back to the default of `1` without failing startup.

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
  data/recent_rolls.json  ← persistent per-chat recent roll history
  /etc/systemd/system/lunch-bot.service  ← systemd unit
```

The design is intentionally flat — no database, no web framework, no async complexity beyond what python-telegram-bot provides out of the box.

All user-facing response strings are written in Traditional Chinese as used in Taiwan (zh-TW, 繁體中文). Simplified Chinese (zh-CN) is not used. All message strings are centralised in a single `messages.py` module so they can be reviewed and updated in one place.

## Components and Interfaces

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

Reads the bot token, data file path, and no-repeat window from environment variables or a `.env` file. Raises a clear error at startup if required values are missing.

```
BOT_TOKEN         — Telegram bot token (required)
DATA_FILE         — path to restaurant-list JSON file (default: data/restaurants.json)
RECENT_ROLLS_FILE — path to recent-roll-history JSON file
                    (optional, default: recent_rolls.json beside DATA_FILE)
NO_REPEAT_WINDOW  — No_Repeat_Window: integer count of most-recent roll results to
                    exclude on the next roll (optional, default: 1)
```

The recent-rolls file lives in the same data folder as `DATA_FILE` (Req 5.3); by default it is `recent_rolls.json` in `DATA_FILE`'s directory, and it can be overridden with `RECENT_ROLLS_FILE`.

`NO_REPEAT_WINDOW` is parsed into an integer `NO_REPEAT_WINDOW` constant at startup by `parse_no_repeat_window(raw)` using the following rules (Req 3a.1, 3a.2, 3a.3):

1. If the variable is **absent**, the value defaults to `1`.
2. If the trimmed value parses as an integer in range `0`–`1000` inclusive, that integer is used.
3. Otherwise, if the value (case-insensitive) is a supported **boolean-style** token, it is mapped for backward compatibility: `true`/`yes`/`on`/`1` → `1`, and `false`/`no`/`off`/`0` → `0`. (`0` and `1` are already covered by the integer rule and are consistent with this mapping.)
4. Any other value — a non-integer, an out-of-range integer (negative or greater than 1000), or an unrecognised token — falls back to the default of `1`, and the bot logs a warning and **continues starting** rather than failing (Req 3a.3).

The value is read once at startup and is constant for the lifetime of the process — there is no runtime command to change it (Req 3a.4).

### storage.py

Thin wrapper around two JSON files, both in the data folder: `DATA_FILE` for restaurant lists and `RECENT_ROLLS_FILE` for per-chat recent roll history. Both are keyed by `chat_id`. Keeping the recent-roll data in its own file leaves the existing `restaurants.json` format untouched (no migration needed) while still satisfying the "same data folder / durable on disk" requirement (Req 5.3).

```python
load(chat_id) -> list[dict]            # restaurant list for a chat (DATA_FILE)
save(chat_id, restaurants: list[dict]) -> None

load_recent_rolls(chat_id) -> list[str]   # ordered recent result names, most recent last
save_recent_rolls(chat_id, history: list[str]) -> None
append_recent_roll(chat_id, name: str, window: int) -> list[str]
    # append name, trim to the most recent `window` entries, persist, and
    # return the updated in-memory history
```

- Both files are read/written atomically (write to temp file, then rename) to avoid corruption on crash, using the same helper used for the restaurant list.
- Restaurant names are stored lowercase for case-insensitive deduplication.
- `Recent_Roll_History` is stored per chat in `RECENT_ROLLS_FILE` (Req 5.3) as an ordered JSON array of lowercase result names with the most recent entry **last**, so it survives restarts (Req 3a.13) and is independent per chat (Req 3a.14).
- `load_recent_rolls` returns an empty list `[]` when the file is missing, the chat has no entry, or the stored value for that chat cannot be read/parsed — i.e. the chat is treated as having no recorded history (Req 3a.10, 3a.17). A read/parse failure is logged.
- `append_recent_roll` appends the new result, trims the history to the most recent `window` entries (keeping the newest), and persists it. If persistence fails, it logs the failure and still returns the updated in-memory history so the caller can keep it for the run (Req 3a.12, 3a.16).
- Recent-roll names are stored using the same lowercase form as restaurant names so membership comparisons against the list are consistent (case-insensitive, Req 3a.6).

### bot.py

Contains one handler per command. Each handler calls storage, applies business logic, and replies.

| Handler | Trigger | Logic |
|---|---|---|
| `cmd_add` | `/add <name> [name2 ...]` | split args into names → for each: validate (reject if contains `\n` or `/`) → check list-full (max 20) → check duplicate → append entry → save → reply with per-name summary |
| `cmd_remove` | `/remove <name>` | load list → find entry by name (case-insensitive) → remove → save → reply |
| `cmd_removeall` | `/removeall` | load list → guard empty → send confirmation message with Yes/No inline keyboard → on confirm: clear list, save, reply success; on cancel: reply cancelled |
| `cmd_roll` | `/roll` | load list → guard empty → load recent history → select via `select_roll` → append + persist result to history → reply with `entry["name"]` |
| `cmd_list` | `/list` | load list → guard empty → format numbered list with name, added_by, added_at → reply |
| `cmd_unknown` | any other message | reply with help text |

**Name validation rules (applied in `cmd_add`):**
- A name is invalid if it contains `\n` (newline) or `/` (forward slash).
- Invalid names are rejected immediately with `ADD_INVALID_NAME`; valid names in the same batch continue to be processed.

**`/add` multi-name behaviour:**
- Arguments are split on whitespace; each token is treated as a separate restaurant name.
- The reply summarises all outcomes (added, duplicate, invalid, list-full) in one message.

**`/roll` selection logic (no-repeat behaviour):**

The core selection is factored into a **pure helper** so it can be property-tested without the Telegram I/O layer:

```python
select_roll(restaurants: list[dict], recent_history: list[str], no_repeat_window: int) -> dict
```

`cmd_roll` loads the restaurant list and guards the empty case (Req 3.2). It then loads the chat's `Recent_Roll_History` and calls `select_roll`, which performs the following bounded decision (Req 3a.15 — never an unbounded retry loop):

1. If `no_repeat_window == 0` → select uniformly at random from the entire list (Req 3a.5). This is the same behaviour as Req 3.1/3.3.
2. If `no_repeat_window >= 1`:
   - If the list has exactly one restaurant → return that restaurant (Req 3a.9).
   - Take the **effective window** = the most recent `min(no_repeat_window, len(recent_history))` entries of `recent_history` (most recent last). If it is empty (no history recorded) → select uniformly at random from the entire list (Req 3a.10).
   - Build the excluded-name set from those window entries, compared **case-insensitively**, ignoring any window name not currently present in the list (Req 3a.11).
   - Compute `Eligible_Restaurants` = list entries whose name is not in the excluded set.
   - **Graceful relaxation** (Req 3a.7): while `Eligible_Restaurants` is empty, drop the **oldest** name from the excluded set (i.e. relax exclusion from oldest to newest) and recompute, until at least one restaurant is eligible. Because there are at most `window` excluded names, this terminates in at most `window` relaxation steps (Req 3a.15).
   - Select uniformly at random from `Eligible_Restaurants` (Req 3a.6, 3a.8).
3. After a result is chosen, `cmd_roll` appends it to the chat's `Recent_Roll_History`, trims to the most recent `no_repeat_window` entries, and persists via `storage.append_recent_roll` (Req 3a.12). On persistence failure the result is still delivered and the updated history is retained in memory for the run (Req 3a.16).

Selection builds the candidate list at most once per relaxation step (at most `1 + window` steps total) and calls `random.choice` a single time — no rejection-sampling loop — which guarantees bounded selection (Req 3a.15). The window is read from `config.NO_REPEAT_WINDOW` only, so its value is constant for the run (Req 3a.4).

### main.py

Wires config → storage → bot handlers → `Application.run_polling()`. Logging is configured to stdout so systemd/journald captures it automatically. At startup it loads each chat's persisted `Recent_Roll_History`; a chat whose stored history cannot be read/parsed is treated as empty and the failure is logged (Req 3a.13, 3a.17).

## Data Models

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

**`RECENT_ROLLS_FILE` (e.g. `data/recent_rolls.json`)** — maps each `chat_id` to an ordered array of that chat's most recent roll result names, with the most recent result **last**. The array holds at most `No_Repeat_Window` entries.

```json
{
  "123456789": ["pizza palace", "sushi spot"],
  "987654321": ["burger barn"]
}
```

- File locations: `DATA_FILE` via its env var; `RECENT_ROLLS_FILE` defaults to `recent_rolls.json` beside `DATA_FILE` and is overridable via `RECENT_ROLLS_FILE`. Both live in the data folder (Req 5.3).
- `name` in the restaurant list is always stored lowercase for case-insensitive deduplication.
- `added_by` is `update.effective_user.username` with `first_name` as fallback.
- `added_at` is stored as an ISO 8601 timestamp with `+08:00` offset (Asia/Taipei) and displayed in Taiwan local time.
- Each `chat_id` in `RECENT_ROLLS_FILE` holds an ordered list of lowercase result names (most recent last), or is absent when no roll has produced a result yet. History is tracked independently per chat (Req 3a.14).
- The stored history for a chat is bounded to the most recent `No_Repeat_Window` names; older entries are dropped as new results are appended (Req 3a.12).
- Because the recent-roll data is a separate file, existing `restaurants.json` files continue to work as-is with no migration; a missing or unparseable `RECENT_ROLLS_FILE` (or an unparseable per-chat entry) is treated as "no recent history recorded" (Req 3a.17).

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

### Property 1: Case-insensitive deduplication

For any restaurant name `n`, adding `n` and then adding any case variant of `n` must result in a rejection, leaving the list containing exactly one entry for that name.

```
∀ name n: add(n) → add(case_variant(n)) → list contains n exactly once
```

**Validates: Requirements 1.5**

### Property 2: Invalid name rejection

For any name containing `\n` (newline) or `/` (forward slash), `cmd_add` must reject it, never append it to the list, and reply with `ADD_INVALID_NAME`.

```
∀ name n where '\n' ∈ n ∨ '/' ∈ n: add(n) → list unchanged
```

**Validates: Requirements 1.6**

### Property 3: Roll result is always a member of the list

For any non-empty restaurant list, any `Recent_Roll_History`, and any `No_Repeat_Window`, `select_roll` returns exactly one element that is a member of the list.

```
∀ non-empty list L, ∀ history H, ∀ window w ≥ 0:
    select_roll(L, H, w) ∈ L
```

**Validates: Requirements 3.1, 3a.9**

### Property 4: Uniform selection over the eligible set

For a fixed non-empty list, history, and window, over many rolls each restaurant in the computed `Eligible_Restaurants` set is selected with approximately equal frequency (verified statistically), and no restaurant outside the eligible set is ever selected.

```
∀ non-empty list L, history H, window w:
    let E = eligible(L, H, w);
    over many rolls, each e ∈ E chosen with freq ≈ 1/|E|, and result ∈ E
```

**Validates: Requirements 3.3, 3a.8**

### Property 5: Full-list eligibility when the window does not constrain

For any non-empty list, when the no-repeat exclusion does not apply — that is, when `No_Repeat_Window == 0`, OR the `Recent_Roll_History` is empty — every restaurant in the list is eligible and the result is selected from the entire list (over many rolls every element is reachable).

```
∀ non-empty list L, ∀ window w, ∀ history H where w == 0 ∨ H == []:
    eligible(L, H, w) == L
```

**Validates: Requirements 3a.5, 3a.10**

### Property 6: Exclusion of the recent window

For any list, `Recent_Roll_History`, and window `w ≥ 1`, when excluding the most recent `min(w, len(H))` history entries still leaves at least one eligible restaurant, the roll result's name does not match (case-insensitively) any of those effective-window names.

```
∀ list L, history H, window w ≥ 1 where eligible-after-exclusion ≠ ∅:
    result = select_roll(L, H, w) ⇒ result.name ∉ recent_window(H, w)  (case-insensitive)
```

**Validates: Requirements 3a.6**

### Property 7: Stale history names exclude nothing

For any list and history where some history names are no longer present in the list, only the names currently present in the list are excluded; absent history names have no effect on the eligible set.

```
∀ list L, history H, window w ≥ 1:
    eligible(L, H, w) excludes only { h ∈ recent_window(H, w) : h ∈ names(L) }
```

**Validates: Requirements 3a.11**

### Property 8: Graceful relaxation and bounded selection

For any non-empty list, any `Recent_Roll_History`, and any window `w ≥ 0` (including when the window covers every name in the list), `select_roll` always returns exactly one element of the list, relaxing the exclusion from oldest to newest as needed, and completes within at most one pass plus at most `w` relaxation steps — never an unbounded or indefinite retry loop.

```
∀ non-empty list L, ∀ history H, ∀ window w ≥ 0:
    select_roll(L, H, w) terminates, returns exactly one e ∈ L,
    using ≤ 1 + w exclusion-relaxation steps
```

**Validates: Requirements 3a.7, 3a.9, 3a.15**

### Property 9: Recent-roll-history persistence round-trip (bounded)

For any chat and any sequence of appended results, persisting the `Recent_Roll_History` and then reloading it (simulating a restart) returns the same ordered history, most recent last, retaining at most `No_Repeat_Window` entries.

```
∀ chat c, ∀ names ns, ∀ window w:
    apply append_recent_roll(c, ·, w) over ns → load_recent_rolls(c)
        == last w entries of ns (most recent last)
```

**Validates: Requirements 3a.12, 3a.13, 5.3**

### Property 10: Per-chat independence of recent roll history

For any two distinct chats, appending to or saving the `Recent_Roll_History` of one chat must not change the `Recent_Roll_History` of the other.

```
∀ chats c1 ≠ c2, ∀ names n1:
    append_recent_roll(c1, n1, w) → load_recent_rolls(c2) is unchanged
```

**Validates: Requirements 3a.14**

### Property 11: Restaurant-list persistence round-trip

For any sequence of add/remove operations, saving and reloading the storage produces an equivalent list of dicts with identical `name`, `added_by`, and `added_at` fields.

```
∀ list[dict] L: save(chat_id, L) → load(chat_id) == L
```

**Validates: Requirements 4.1, 5.1, 5.2**

### Property 12: No_Repeat_Window parsing and default

For any configuration input string, `parse_no_repeat_window` returns: the integer itself for integers in range `0`–`1000`; `1` for truthy boolean-style tokens (`true`/`yes`/`on`, case-insensitive) and `0` for falsy tokens (`false`/`no`/`off`, case-insensitive); and the default `1` for absent, non-integer, out-of-range, or unrecognised values — never raising.

```
∀ env string s:
    s absent                          → 1
    s ∈ int ∧ 0 ≤ s ≤ 1000            → int(s)
    s truthy-token                    → 1
    s falsy-token                     → 0
    otherwise                         → 1  (no exception)
```

**Validates: Requirements 3a.1, 3a.2, 3a.3**

### Non-property checks

The following acceptance criteria are verified by example-based, smoke, or config-wiring tests rather than property-based tests:

- **Req 3a.4** (window read once at startup, constant for the run): smoke check that `select_roll` receives the window from `config.NO_REPEAT_WINDOW` and there is no runtime mutation path.
- **Req 3a.16** (persistence failure after a roll): example test — mock `save_recent_rolls` to fail, assert the roll result is still returned, the in-memory history is updated, and the failure is logged.
- **Req 3a.17** (unreadable history at startup): example test — corrupt/missing `recent_rolls.json`, assert `load_recent_rolls` returns `[]` per chat, startup proceeds, failure logged.
- **Req 4.1 / 4.2** (list rendering and empty-list message): example tests.
- **Req 6.1 / 6.2** (storage-failure notification, unknown-command help): example tests with mocked failures.
- **Req 7.1–7.3** (zh-TW localization): review/smoke check of `messages.py`.
- **Req 8.5** (missing `BOT_TOKEN` fails fast): example test — unset `BOT_TOKEN`, assert startup raises a clear error before any network call.

## Error Handling

All reply strings are in Traditional Chinese (zh-TW) sourced from `messages.py`.

| Situation | Behavior |
|---|---|
| Storage read fails | Log error, reply「⚠️ 操作失敗，請稍後再試。」 |
| Storage write fails | Log error, reply「⚠️ 操作失敗，請稍後再試。」 |
| Recent-roll-history persistence fails during `/roll` (Req 3a.16) | Log error; the roll result is still replied to the user, and the updated history is retained in memory for the rest of the run. Failing to persist must not block returning a pick (worst case: after a restart, the unpersisted results are forgotten). |
| Recent-roll-history unreadable / unparseable at startup (Req 3a.17) | Treat the affected chat's history as empty (`[]`), log the failure, and continue starting. |
| Invalid / out-of-range / unset `NO_REPEAT_WINDOW` value (Req 3a.3) | Fall back to the default window of `1`, log a warning, and continue starting rather than failing. |
| `/add` with no argument | Reply with usage:「用法：/add <餐廳名稱> [餐廳名稱2 ...]」 |
| `/add` name contains `\n` or `/` | Reply with「⚠️ 餐廳名稱格式不正確，名稱不可包含換行或斜線：{name}」 |
| `/remove` with no argument | Reply with usage:「用法：/remove <餐廳名稱>」 |
| `/removeall` on empty list | Reply「清單已經是空的了。」 |
| `/removeall` — user cancels confirmation | Reply「已取消，清單保持不變。」 |
| Unknown command or plain text | Reply with help listing all five commands (zh-TW) |
| Missing `BOT_TOKEN` at startup | Raise `RuntimeError` with descriptive message, exit non-zero |

## Testing Strategy

A dual approach is used: example/edge-case unit tests for specific behaviours, and property-based tests for universal properties.

**Property-based testing:**
- Library: [Hypothesis](https://hypothesis.readthedocs.io/) (the standard choice for Python).
- Each property in the Correctness Properties section is implemented by a single property-based test running a minimum of 100 iterations.
- The roll selection logic is factored into the pure helper `select_roll(restaurants, recent_history, no_repeat_window) -> entry` so Properties 3–8 can be tested without the Telegram I/O layer. Generators cover: window `0`, window `≥ 1` up to the list size and beyond, empty history, history longer than the window, history names not present in the list, and single-restaurant lists (Req 3a.9 edge case).
- Storage round-trip, bounded history, and per-chat independence (Properties 9, 10, 11) are tested against temporary `DATA_FILE` and `RECENT_ROLLS_FILE` paths, exercising `save`/`load`, `append_recent_roll`, `save_recent_rolls`, and `load_recent_rolls`.
- Config parsing (Property 12) is tested against `parse_no_repeat_window` with generated integer strings (in and out of range), boolean-style tokens in mixed case, absent values, and arbitrary junk strings.
- Each property test is tagged with a comment referencing its design property, e.g.
  `# Feature: telegram-lunch-bot, Property 8: Graceful relaxation and bounded selection`.

**Unit / example / smoke tests:**
- Req 3a.4 — smoke test that `cmd_roll` sources the window from `config.NO_REPEAT_WINDOW` and no runtime path mutates it.
- Req 3a.16 — example test: mock `save_recent_rolls` to raise; assert the roll result is still returned and the in-memory history is updated, with the failure logged.
- Req 3a.17 — example test: a corrupt or missing `recent_rolls.json` (or a corrupt per-chat entry) makes `load_recent_rolls` return `[]` and startup proceeds, with the failure logged.
- Req 8.5 — example test that an unset `BOT_TOKEN` raises at startup before any network call.
- Edge cases: single-restaurant list (Req 3a.9), empty history (Req 3a.10), and history names removed from the list (Req 3a.11).
- Missing `RECENT_ROLLS_FILE`: `load_recent_rolls` returns `[]` for any chat (treated as "no recent history recorded").

**Existing tests** (`tests/test_config.py`, `tests/test_storage.py`, `tests/test_restaurant_names.py`, `tests/test_invalid_name_rejection.py`, `tests/test_no_repeat_parsing.py`, `tests/test_select_roll.py`) remain valid but MUST be updated for the new design: `test_no_repeat_parsing.py` for the integer `parse_no_repeat_window`, `test_select_roll.py` for the `(restaurants, recent_history, no_repeat_window)` signature and window/relaxation semantics, and `test_storage.py` for the `recent_rolls` functions and the separate `RECENT_ROLLS_FILE`.

## Dependencies

```
python-telegram-bot>=20.0
python-dotenv>=1.0
```

Python 3.10+ (available on Ubuntu 22.04 LTS and later).

No GUI libraries. No database. No external services beyond the Telegram Bot API.

# Implementation Plan: Telegram Lunch Bot

## Overview

Implement a flat Python project that runs as a Telegram bot for random lunch selection. Tasks follow the module dependency order: messages → config → storage → roll selection helper → bot handlers → main entry point → deployment file.

The `/roll` command supports a configurable no-repeat behaviour governed by the `No_Repeat_Window` — an integer configuration value (0–1000, default 1) read once at startup from the environment / `.env` file. `0` disables the behaviour, `1` excludes only the single most recent result (the earlier block-once behaviour), and larger values exclude a longer run of recent picks. Each chat's bounded `Recent_Roll_History` (an ordered list of recent result names, most recent last) is persisted to a separate `RECENT_ROLLS_FILE` in the data folder so the behaviour survives restarts, and the selection degrades gracefully — relaxing the exclusion oldest-first — when excluding the recent window would otherwise leave no restaurant to pick. The selection logic is factored into a pure helper (`select_roll`) so it can be property-tested without the Telegram I/O layer.

Property numbers below match the Correctness Properties section of `design.md` (Properties 1–12).

## Tasks

- [x] 1. Update `messages.py` with new zh-TW string constants
  - Add: ADD_INVALID_NAME, ADD_USAGE (updated for multi-name), REMOVEALL_CONFIRM, REMOVEALL_YES, REMOVEALL_NO, REMOVEALL_SUCCESS, REMOVEALL_CANCEL, REMOVEALL_EMPTY
  - Update HELP_TEXT to include `/removeall` and multi-name `/add` usage
  - No Simplified Chinese characters; use Taiwan-region phrasing
  - _Requirements: 1.4, 1.6, 2a.1, 2a.2, 2a.3, 2a.4, 7.1, 7.2, 7.3_

- [ ] 2. Update `config.py` with environment variable loading (token, data file, recent-rolls file, no-repeat window)
  - [x] 2.1 Implement core config loading using `python-dotenv`
    - Read `BOT_TOKEN` (required) and `DATA_FILE` (default: `data/restaurants.json`) from env / `.env`
    - Raise `RuntimeError` with a descriptive message if `BOT_TOKEN` is missing
    - _Requirements: 8.5, 6.1_

  - [ ] 2.2 Add `RECENT_ROLLS_FILE` and `NO_REPEAT_WINDOW` configuration
    - Read `RECENT_ROLLS_FILE` from env; default to `recent_rolls.json` in the same directory as `DATA_FILE`
    - Implement pure helper `parse_no_repeat_window(raw: str | None) -> int` and expose the result as the `NO_REPEAT_WINDOW` integer constant, using these rules: absent → default `1`; trimmed value that parses as an integer in range `0`–`1000` inclusive → that integer; otherwise a boolean-style token (case-insensitive) `true`/`yes`/`on` → `1` and `false`/`no`/`off` → `0`; any other value (non-integer, out-of-range, or unrecognised) → default `1` while logging a warning and continuing startup (never raising)
    - Read once at startup; value is constant for the process lifetime (no runtime mutation path)
    - _Requirements: 3a.1, 3a.2, 3a.3, 3a.4, 5.3_

  - [ ]* 2.3 Write property test for No_Repeat_Window parsing and default (Property 12)
    - **Property 12: No_Repeat_Window parsing and default**
    - **Validates: Requirements 3a.1, 3a.2, 3a.3**
    - For any input string, assert `parse_no_repeat_window` returns: the integer itself for integers in `0`–`1000`; `1` for truthy tokens and `0` for falsy tokens (mixed case); and the default `1` for absent, non-integer, out-of-range, or junk values — never raising

  - [x]* 2.4 Write example test for missing token fails fast (non-property check)
    - **Non-property check (example test)**
    - **Validates: Requirements 8.5**
    - Unset `BOT_TOKEN` and assert `RuntimeError` is raised on config load, before any network call
    - Already implemented in `tests/test_config.py`

- [ ] 3. Update `storage.py` with atomic JSON persistence for both files
  - [x] 3.1 Implement `load(chat_id) -> list[dict]` and `save(chat_id, restaurants: list[dict]) -> None`
    - Key the restaurant list by `chat_id` in `DATA_FILE`; each entry is a dict with `name` (str), `added_by` (str), and `added_at` (ISO 8601 str with +08:00 offset)
    - Write atomically: write to a temp file then `os.replace` to avoid corruption
    - Return empty list when file does not exist or `chat_id` is absent
    - _Requirements: 5.1, 5.2_

  - [ ] 3.2 Implement recent-roll history functions in a separate `RECENT_ROLLS_FILE`
    - `load_recent_rolls(chat_id) -> list[str]`: return the chat's ordered history (most recent last); return `[]` when the file is missing, the chat has no entry, or the stored value cannot be read/parsed, logging read/parse failures (Req 3a.10, 3a.17)
    - `save_recent_rolls(chat_id, history: list[str]) -> None`: persist the ordered history for the chat, keyed by `chat_id`, using the same atomic write-then-rename helper as the restaurant list
    - `append_recent_roll(chat_id, name: str, window: int) -> list[str]`: append the new result, trim to the most recent `window` entries (keeping the newest), persist, and return the updated in-memory history; on persistence failure, log and still return the updated in-memory history (Req 3a.12, 3a.16)
    - Store names lowercase (consistent with restaurant-name storage) for case-insensitive membership comparison; keep `restaurants.json` format untouched (no migration)
    - Track history independently per chat (Req 3a.14)
    - _Requirements: 3a.12, 3a.13, 3a.14, 3a.16, 3a.17, 5.3_

  - [x]* 3.3 Write property test for restaurant-list persistence round-trip (Property 11)
    - **Property 11: Restaurant-list persistence round-trip**
    - **Validates: Requirements 4.1, 5.1, 5.2**
    - For any arbitrary `list[dict]` `L` (each dict with `name`, `added_by`, `added_at`), assert `load(chat_id)` equals `L` after `save(chat_id, L)`
    - Already implemented in `tests/test_storage.py`

  - [ ]* 3.4 Write property test for recent-roll-history persistence round-trip (Property 9)
    - **Property 9: Recent-roll-history persistence round-trip (bounded)**
    - **Validates: Requirements 3a.12, 3a.13, 5.3**
    - For any chat `c`, any sequence of names `ns`, and any window `w`, apply `append_recent_roll(c, ·, w)` over `ns`, then assert a fresh `load_recent_rolls(c)` (simulating a restart) equals the last `w` entries of `ns`, most recent last

  - [ ]* 3.5 Write property test for per-chat independence of recent roll history (Property 10)
    - **Property 10: Per-chat independence of recent roll history**
    - **Validates: Requirements 3a.14**
    - For any two distinct chats `c1 != c2`, assert `append_recent_roll(c1, n1, w)` (or `save_recent_rolls(c1, ...)`) does not change `load_recent_rolls(c2)`

  - [ ]* 3.6 Write example test for graceful handling of missing/corrupt history (non-property check)
    - **Non-property check (example test)**
    - **Validates: Requirements 3a.17**
    - Assert `load_recent_rolls` returns `[]` when `RECENT_ROLLS_FILE` is missing, and returns `[]` and logs when the file or a per-chat entry is corrupt/unparseable

- [ ] 4. Implement the pure roll selection helper
  - [ ] 4.1 Implement `select_roll(restaurants, recent_history, no_repeat_window) -> entry`
    - Pure function with no Telegram or storage I/O, so it can be tested directly
    - If `no_repeat_window == 0` → select uniformly at random from the entire list (Req 3a.5)
    - If `no_repeat_window >= 1`: single-restaurant list → return that restaurant (Req 3a.9); take the effective window = the most recent `min(no_repeat_window, len(recent_history))` entries; if empty → select uniformly from the entire list (Req 3a.10)
    - Build the excluded-name set from the effective-window entries, compared case-insensitively, ignoring any window name not currently present in the list (Req 3a.11); compute `Eligible_Restaurants` = entries not in the excluded set
    - Graceful relaxation (Req 3a.7): while `Eligible_Restaurants` is empty, drop the oldest excluded name (relax oldest → newest) and recompute, terminating in at most `window` relaxation steps
    - Build the candidate list at most once per relaxation step (at most `1 + window` steps total) and call `random.choice` a single time — no rejection-sampling loop (Req 3a.15)
    - _Requirements: 3.1, 3.3, 3a.5, 3a.6, 3a.7, 3a.8, 3a.9, 3a.10, 3a.11, 3a.15_

  - [ ]* 4.2 Write property test for roll result always a member of the list (Property 3)
    - **Property 3: Roll result is always a member of the list**
    - **Validates: Requirements 3.1, 3a.9**
    - For any non-empty list, any history, and any window `w >= 0`, assert `select_roll(...)` returns exactly one element that is a member of the list

  - [ ]* 4.3 Write property test for uniform selection over the eligible set (Property 4)
    - **Property 4: Uniform selection over the eligible set**
    - **Validates: Requirements 3.3, 3a.8**
    - For a fixed non-empty list, history, and window, over many rolls assert each restaurant in the computed eligible set is chosen with frequency ≈ `1/|E|` within tolerance and no restaurant outside the eligible set is ever selected

  - [ ]* 4.4 Write property test for full-list eligibility when unconstrained (Property 5)
    - **Property 5: Full-list eligibility when the window does not constrain**
    - **Validates: Requirements 3a.5, 3a.10**
    - When `no_repeat_window == 0` OR `recent_history == []`, assert the eligible set equals the entire list and, over many rolls, every element is reachable

  - [ ]* 4.5 Write property test for exclusion of the recent window (Property 6)
    - **Property 6: Exclusion of the recent window**
    - **Validates: Requirements 3a.6**
    - For any list, history, and window `w >= 1` where excluding the most recent `min(w, len(H))` entries still leaves at least one eligible restaurant, assert the result's name does not match (case-insensitively) any of those effective-window names

  - [ ]* 4.6 Write property test for stale history names excluding nothing (Property 7)
    - **Property 7: Stale history names exclude nothing**
    - **Validates: Requirements 3a.11**
    - For any list and history where some history names are absent from the list, assert only names currently present in the list are excluded and absent history names have no effect on the eligible set

  - [ ]* 4.7 Write property test for graceful relaxation and bounded selection (Property 8)
    - **Property 8: Graceful relaxation and bounded selection**
    - **Validates: Requirements 3a.7, 3a.9, 3a.15**
    - For any non-empty list, any history, and any window `w >= 0` (including when the window covers every name in the list), assert `select_roll` terminates, returns exactly one element of the list, and completes within at most `1 + w` exclusion-relaxation steps (no unbounded retry loop)

- [ ] 5. Update `bot.py` command handlers
  - [x] 5.1 Update `cmd_add` handler for multi-name and validation
    - Split args on whitespace; each token is a separate restaurant name
    - For each name: reject if it contains `\n` or `/` (reply ADD_INVALID_NAME); lowercase for dedup check; check duplicate (reply ADD_DUPLICATE); append entry with original casing; save
    - Reply with a single summary message covering all outcomes
    - Catch storage exceptions, log error, reply STORAGE_ERROR
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 4.1, 5.2, 6.1_

  - [ ]* 5.2 Write property test for case-insensitive deduplication (Property 1)
    - **Property 1: Case-insensitive deduplication**
    - **Validates: Requirements 1.5**
    - For any name `n`, after adding `n` then any case variant, assert the list contains `n` exactly once

  - [x]* 5.3 Write property test for invalid name rejection (Property 2)
    - **Property 2: Invalid name rejection**
    - **Validates: Requirements 1.6**
    - For any name containing `\n` or `/`, assert `cmd_add` rejects it, the list is unchanged, and the reply is ADD_INVALID_NAME
    - Already implemented in `tests/test_invalid_name_rejection.py`

  - [x] 5.4 Implement `cmd_remove` handler
    - Parse argument; reply REMOVE_USAGE if missing
    - Load list; find entry (case-insensitive); remove; save; reply REMOVE_SUCCESS or REMOVE_NOT_FOUND
    - Catch storage exceptions, log error, reply STORAGE_ERROR
    - _Requirements: 2.1, 2.2, 2.3, 5.2, 6.1_

  - [x] 5.5 Implement `cmd_removeall` handler and callback
    - Load list; guard empty (reply REMOVEALL_EMPTY)
    - Send REMOVEALL_CONFIRM with Yes/No inline keyboard (InlineKeyboardMarkup)
    - On "Yes" callback: clear list, save, edit message to REMOVEALL_SUCCESS
    - On "No" callback: edit message to REMOVEALL_CANCEL, leave list unchanged
    - Register a `CallbackQueryHandler` in `main.py` to handle the inline keyboard responses
    - Catch storage exceptions, log error, reply STORAGE_ERROR
    - _Requirements: 2a.1, 2a.2, 2a.3, 2a.4, 5.2, 6.1_

  - [ ] 5.6 Update `cmd_roll` handler to use the No_Repeat_Window-aware selection logic
    - Load list; guard empty (reply ROLL_EMPTY)
    - Load the chat's `Recent_Roll_History` via `storage.load_recent_rolls(chat_id)`
    - Select using `select_roll(restaurants, recent_history, config.NO_REPEAT_WINDOW)` (read the window from `config.NO_REPEAT_WINDOW` only)
    - Append and persist the result via `storage.append_recent_roll(chat_id, name, config.NO_REPEAT_WINDOW)`; if persistence fails, log the error but still reply with the pick (Req 3a.16)
    - Reply ROLL_RESULT with the selected entry's name
    - Catch storage read exceptions, log error, reply STORAGE_ERROR
    - _Requirements: 3.1, 3.2, 3.3, 3a.5, 3a.6, 3a.7, 3a.8, 3a.9, 3a.10, 3a.11, 3a.12, 3a.16, 6.1_

  - [ ]* 5.7 Write smoke test that `/roll` reads the window from config (non-property check)
    - **Non-property check (smoke test)**
    - **Validates: Requirements 3a.4**
    - Assert `cmd_roll` sources the window from `config.NO_REPEAT_WINDOW` and there is no runtime path that mutates it

  - [ ]* 5.8 Write example test for persistence failure after a roll (non-property check)
    - **Non-property check (example test)**
    - **Validates: Requirements 3a.16**
    - Mock `save_recent_rolls`/`append_recent_roll` persistence to fail; assert the roll result is still returned, the in-memory history is updated, and the failure is logged

  - [x] 5.9 Implement `cmd_list` handler
    - Load list; guard empty (reply LIST_EMPTY); format each entry using LIST_ITEM with `name`, `added_by`, and `added_at` (formatted in Asia/Taipei timezone); join lines and reply with LIST_HEADER
    - Catch storage exceptions, log error, reply STORAGE_ERROR
    - _Requirements: 4.1, 4.2, 6.1_

  - [x] 5.10 Implement `cmd_unknown` handler
    - Reply with HELP_TEXT for any unrecognised command or plain text
    - _Requirements: 6.2_

- [ ] 6. Checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Wire everything together in `main.py`
  - [ ] 7.1 Wire config → storage → bot handlers → `Application.run_polling()`
    - Import `config`; register all command handlers and the `CallbackQueryHandler` for `cmd_removeall` on the `Application`
    - Load each chat's persisted `Recent_Roll_History` at startup so recent-repeat avoidance applies after a restart; treat a chat whose stored history cannot be read/parsed as empty and log the failure (Req 3a.13, 3a.17)
    - Configure `logging` to stdout so systemd/journald captures output
    - _Requirements: 3a.13, 3a.17, 8.1, 8.4_

  - [ ]* 7.2 Write example test for startup loading of unreadable history (non-property check)
    - **Non-property check (example test)**
    - **Validates: Requirements 3a.13, 3a.17**
    - With a corrupt or missing `recent_rolls.json` (or a corrupt per-chat entry), assert startup proceeds, each affected chat's history loads as `[]`, and the failure is logged

- [x] 8. Create `requirements.txt` and `deploy/lunch-bot.service`
  - [x] 8.1 Write `requirements.txt`
    - Include `python-telegram-bot>=20.0` and `python-dotenv>=1.0`
    - _Requirements: 8.1_

  - [x] 8.2 Write `deploy/lunch-bot.service` systemd unit file
    - Set `After=network.target`, `Restart=on-failure`, `RestartSec=5`
    - Use `EnvironmentFile=/opt/lunch-bot/.env` for secrets
    - Include `[Install] WantedBy=multi-user.target` for auto-start on boot
    - _Requirements: 8.2, 8.3, 8.4, 8.5_

- [ ] 9. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Property tests use `hypothesis` (in `requirements-dev.txt`); each property test is tagged with a comment referencing its design property number
- Property numbers and "Validates" references match the Correctness Properties section of `design.md` (Properties 1–12)
- Non-property checks are verified by example/smoke tests: Req 3a.4 (window read once at startup), Req 3a.16 (persistence failure after a roll), Req 3a.17 (unreadable history at startup), and Req 8.5 (missing token fails fast)
- Each task references specific requirements for traceability
- All user-facing strings must come from `messages.py`; no inline string literals in handlers

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.2", "3.2", "4.1"] },
    { "id": 1, "tasks": ["2.3", "3.4", "3.5", "3.6", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "5.2", "5.6"] },
    { "id": 2, "tasks": ["5.7", "5.8", "7.1"] },
    { "id": 3, "tasks": ["7.2"] }
  ]
}
```

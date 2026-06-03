# Implementation Plan: Telegram Lunch Bot

## Overview

Implement a flat Python project that runs as a Telegram bot for random lunch selection. Tasks follow the module dependency order: messages → config → storage → roll selection helper → bot handlers → main entry point → deployment file.

The `/roll` command supports a configurable no-repeat behaviour (`No_Repeat_Toggle`, default enabled) that avoids returning the same restaurant on two successive rolls in the same chat. The most recent roll result (`Previous_Roll_Result`) is persisted per chat to a separate `PREVIOUS_ROLL_FILE` in the data folder so the behaviour survives restarts. The selection logic is factored into a pure helper (`select_roll`) so it can be property-tested without the Telegram I/O layer.

Property numbers below match the Correctness Properties section of `design.md` (Properties 1–11).

## Tasks

- [x] 1. Update `messages.py` with new zh-TW string constants
  - Add: ADD_INVALID_NAME, ADD_USAGE (updated for multi-name), REMOVEALL_CONFIRM, REMOVEALL_YES, REMOVEALL_NO, REMOVEALL_SUCCESS, REMOVEALL_CANCEL, REMOVEALL_EMPTY
  - Update HELP_TEXT to include `/removeall` and multi-name `/add` usage
  - No Simplified Chinese characters; use Taiwan-region phrasing
  - _Requirements: 1.4, 1.6, 2a.1, 2a.2, 2a.3, 2a.4, 7.1, 7.2, 7.3_

- [ ] 2. Update `config.py` with environment variable loading (token, data file, no-repeat toggle)
  - [x] 2.1 Implement core config loading using `python-dotenv`
    - Read `BOT_TOKEN` (required) and `DATA_FILE` (default: `data/restaurants.json`) from env / `.env`
    - Raise `RuntimeError` with a descriptive message if `BOT_TOKEN` is missing
    - _Requirements: 8.5, 6.1_

  - [ ] 2.2 Add `PREVIOUS_ROLL_FILE` and `NO_REPEAT` configuration
    - Read `PREVIOUS_ROLL_FILE` from env; default to `previous_roll.json` in the same directory as `DATA_FILE`
    - Parse `NO_REPEAT` into a boolean constant using a truthy/falsy convention (`1/true/yes/on` → enabled, `0/false/no/off` → disabled, case-insensitive); default to `True` when absent; fall back to the default for unrecognised values rather than failing startup
    - Read once at startup; value is constant for the process lifetime (no runtime mutation path)
    - Factor the parsing into a small pure helper (e.g. `parse_no_repeat(value: str | None) -> bool`) so it can be property-tested
    - _Requirements: 3a.1, 3a.2, 5.3_

  - [ ]* 2.3 Write property test for No_Repeat_Toggle parsing and default (Property 10)
    - **Property 10: No_Repeat_Toggle parsing and default**
    - **Validates: Requirements 3a.1**
    - For any input string, assert `parse_no_repeat` matches the truthy/falsy convention; assert an absent value defaults to enabled (`True`)

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

  - [ ] 3.2 Implement `load_previous_roll(chat_id) -> str | None` and `save_previous_roll(chat_id, name: str) -> None`
    - Persist per-chat previous roll results in a separate `PREVIOUS_ROLL_FILE` (keyed by `chat_id`), leaving `restaurants.json` format untouched (no migration)
    - Use the same atomic write-then-rename helper as the restaurant list
    - Store the name in lowercase form (consistent with restaurant-name storage) for reliable membership comparison
    - `load_previous_roll` returns `None` when the file is missing or the chat has no recorded result
    - _Requirements: 3a.8, 3a.10, 5.3_

  - [x]* 3.3 Write property test for round-trip persistence of the restaurant list (Property 2)
    - **Property 2: Round-trip persistence of the restaurant list**
    - **Validates: Requirements 4.1, 5.1, 5.2**
    - For any arbitrary `list[dict]` `L` (each dict with `name`, `added_by`, `added_at`), assert `load(chat_id)` equals `L` after `save(chat_id, L)`
    - Already implemented in `tests/test_storage.py`

  - [ ]* 3.4 Write property test for previous-roll persistence round-trip (Property 7)
    - **Property 7: Previous-roll persistence round-trip**
    - **Validates: Requirements 3a.8, 3a.9, 5.3**
    - For any chat `c` and name `n`, assert `load_previous_roll(c)` equals `n` after `save_previous_roll(c, n)` (using a fresh read to simulate a restart)

  - [ ]* 3.5 Write property test for per-chat independence of the previous roll result (Property 8)
    - **Property 8: Per-chat independence of the previous roll result**
    - **Validates: Requirements 3a.10**
    - For any two distinct chats `c1 != c2`, assert `save_previous_roll(c1, n1)` does not change `load_previous_roll(c2)`

  - [ ]* 3.6 Write unit test for missing `PREVIOUS_ROLL_FILE` (edge case)
    - Assert `load_previous_roll` returns `None` for any chat when `PREVIOUS_ROLL_FILE` does not exist
    - _Requirements: 3a.5, 5.3_

- [ ] 4. Implement the pure roll selection helper
  - [ ] 4.1 Implement `select_roll(restaurants, previous, no_repeat) -> entry`
    - Pure function with no Telegram or storage I/O, so it can be tested directly
    - If `no_repeat` is disabled → select uniformly at random from the entire list
    - If `no_repeat` is enabled: single-restaurant list → return that restaurant; `previous` is `None` or not present in the list → select uniformly from the entire list; otherwise → select uniformly from the list excluding the entry whose name equals `previous`
    - Build the candidate list once and call `random.choice` a single time (no rejection-sampling loop) to guarantee bounded selection
    - _Requirements: 3.1, 3.3, 3a.3, 3a.4, 3a.5, 3a.6, 3a.7, 3a.11_

  - [ ]* 4.2 Write property test for roll result always from the list (Property 4)
    - **Property 4: Roll result is always from the list**
    - **Validates: Requirements 3.1**
    - For any non-empty list and any toggle/previous combination, assert `select_roll(...)` returns a member of the list

  - [ ]* 4.3 Write property test for uniform random selection (Property 3)
    - **Property 3: Uniform random selection**
    - **Validates: Requirements 3.3**
    - With no-repeat disabled, over a large number of rolls on a list of `k` items assert each item frequency ≈ `1/k` within tolerance

  - [ ]* 4.4 Write property test for no-repeat avoids the previous result (Property 5)
    - **Property 5: No-repeat avoids the previous result**
    - **Validates: Requirements 3a.3, 3a.4**
    - With no-repeat enabled and `previous` present in the list: if `|L| >= 2` assert the result is in the list and not equal to `previous`; if `|L| == 1` assert the single element is returned

  - [ ]* 4.5 Write property test for full-list eligibility when no-repeat does not constrain (Property 6)
    - **Property 6: Full-list eligibility when no-repeat does not constrain**
    - **Validates: Requirements 3a.5, 3a.6, 3a.7**
    - When the toggle is disabled, OR `previous` is `None`, OR `previous` is not in the list, assert the result is from the entire list and, over many rolls, every element is reachable

  - [ ]* 4.6 Write property test for bounded selection (Property 9)
    - **Property 9: Bounded selection**
    - **Validates: Requirements 3a.11**
    - For any non-empty list and any toggle/previous combination, assert the candidate set is non-empty and `select_roll` returns exactly one element (no looping or indefinite retry)

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

  - [x]* 5.3 Write property test for invalid name rejection (Property 11)
    - **Property 11: Invalid name rejection**
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

  - [ ] 5.6 Update `cmd_roll` handler to use the no-repeat-aware selection logic
    - Load list; guard empty (reply ROLL_EMPTY)
    - Load `Previous_Roll_Result` via `storage.load_previous_roll(chat_id)`
    - Select using `select_roll(restaurants, previous, config.NO_REPEAT)` (read the toggle from `config.NO_REPEAT` only)
    - Record and persist the result via `storage.save_previous_roll(chat_id, name)`; if persistence fails, log the error but still reply with the pick
    - Reply ROLL_RESULT with the selected entry's name
    - Catch storage read exceptions, log error, reply STORAGE_ERROR
    - _Requirements: 3.1, 3.2, 3.3, 3a.2, 3a.3, 3a.4, 3a.5, 3a.6, 3a.7, 3a.8, 6.1_

  - [ ]* 5.7 Write smoke test that `/roll` reads the toggle from config (non-property check)
    - **Non-property check (smoke test)**
    - **Validates: Requirements 3a.2**
    - Assert `cmd_roll` consults `config.NO_REPEAT` and there is no runtime path that mutates the toggle

  - [x] 5.8 Implement `cmd_list` handler
    - Load list; guard empty (reply LIST_EMPTY); format each entry using LIST_ITEM with `name`, `added_by`, and `added_at` (formatted in Asia/Taipei timezone); join lines and reply with LIST_HEADER
    - Catch storage exceptions, log error, reply STORAGE_ERROR
    - _Requirements: 4.1, 4.2, 6.1_

  - [x] 5.9 Implement `cmd_unknown` handler
    - Reply with HELP_TEXT for any unrecognised command or plain text
    - _Requirements: 6.2_

- [ ] 6. Checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Wire everything together in `main.py`
  - [ ] 7.1 Wire config → storage → bot handlers → `Application.run_polling()`
    - Import `config`; register all command handlers and the `CallbackQueryHandler` for `cmd_removeall` on the `Application`
    - Ensure the no-repeat-aware `cmd_roll` and the previous-roll storage are loaded on startup so duplicate-avoidance applies after a restart
    - Configure `logging` to stdout so systemd/journald captures output
    - _Requirements: 3a.9, 8.1, 8.4_

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
- Property numbers and "Validates" references match the Correctness Properties section of `design.md` (Properties 1–11)
- Requirements 3a.2 (toggle read once at startup) and 8.5 (missing token fails fast) are verified by non-property example/smoke tests
- Each task references specific requirements for traceability
- All user-facing strings must come from `messages.py`; no inline string literals in handlers

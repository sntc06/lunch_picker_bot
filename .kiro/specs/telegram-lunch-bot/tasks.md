# Implementation Plan: Telegram Lunch Bot

## Overview

Implement a flat Python project that runs as a Telegram bot for random lunch selection. Tasks follow the module dependency order: messages → config → storage → bot handlers → main entry point → deployment file.

## Tasks

- [x] 1. Update `messages.py` with new zh-TW string constants
  - Add: ADD_INVALID_NAME, ADD_LIST_FULL, ADD_USAGE (updated for multi-name), REMOVEALL_CONFIRM, REMOVEALL_YES, REMOVEALL_NO, REMOVEALL_SUCCESS, REMOVEALL_CANCEL, REMOVEALL_EMPTY
  - Update HELP_TEXT to include `/removeall` and multi-name `/add` usage
  - No Simplified Chinese characters; use Taiwan-region phrasing
  - _Requirements: 1.4, 1.6, 1.7, 2a.1–4, 7.1, 7.2, 7.3_

- [x] 2. Create `config.py` with environment variable loading
  - [x] 2.1 Implement config loading using `python-dotenv`
    - Read `BOT_TOKEN` (required) and `DATA_FILE` (default: `data/restaurants.json`) from env / `.env`
    - Raise `RuntimeError` with a descriptive message if `BOT_TOKEN` is missing
    - _Requirements: 8.5, 6.1 (config error path)_

  - [x] 2.2 Write property test for missing token fails fast (Property 5)
    - **Property 5: Config missing token fails fast**
    - **Validates: Requirements 8.5**
    - Unset `BOT_TOKEN` and assert `RuntimeError` is raised before any network call

- [x] 3. Create `storage.py` with atomic JSON persistence
  - [x] 3.1 Implement `load(chat_id) -> list[dict]` and `save(chat_id, restaurants: list[dict]) -> None`
    - Key storage by `chat_id`; each entry is a dict with `name` (str), `added_by` (str), and `added_at` (ISO 8601 str with +08:00 offset)
    - Write atomically: write to a temp file then `os.replace` to avoid corruption
    - Return empty list when file does not exist or chat_id is absent
    - _Requirements: 5.1, 5.2_

  - [x] 3.2 Write property test for round-trip persistence (Property 2)
    - **Property 2: Round-trip persistence**
    - **Validates: Requirements 4.1, 5.1, 5.2**
    - For any arbitrary `list[dict]` `L` (each dict with `name`, `added_by`, `added_at`), assert `load(chat_id)` equals `L` after `save(chat_id, L)`

- [x] 4. Update `bot.py` command handlers
  - [x] 4.1 Update `cmd_add` handler for multi-name and validation
    - Split args on whitespace; each token is a separate restaurant name
    - For each name: reject if contains `\n` or `/` (reply ADD_INVALID_NAME); lowercase for dedup check; check list-full (max 20, reply ADD_LIST_FULL); check duplicate (reply ADD_DUPLICATE); append entry with original casing; save
    - Reply with a single summary message covering all outcomes
    - Catch storage exceptions, log error, reply STORAGE_ERROR
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 4.1, 5.2, 6.1_

  - [ ]* 4.2 Write property test for case-insensitive deduplication (Property 1)
    - **Property 1: Case-insensitive deduplication**
    - **Validates: Requirements 1.5**
    - For any name `n`, after adding `n` then any case variant, assert list contains `n` exactly once

  - [x] 4.3 Implement `cmd_remove` handler
    - Parse argument; reply REMOVE_USAGE if missing
    - Load list; find entry (case-insensitive); remove; save; reply REMOVE_SUCCESS or REMOVE_NOT_FOUND
    - Catch storage exceptions, log error, reply STORAGE_ERROR
    - _Requirements: 2.1, 2.2, 2.3, 5.2, 6.1_

  - [x] 4.3a Implement `cmd_removeall` handler and callback
    - Load list; guard empty (reply REMOVEALL_EMPTY)
    - Send REMOVEALL_CONFIRM with Yes/No inline keyboard (InlineKeyboardMarkup)
    - On "Yes" callback: clear list, save, edit message to REMOVEALL_SUCCESS
    - On "No" callback: edit message to REMOVEALL_CANCEL, leave list unchanged
    - Register a `CallbackQueryHandler` in `main.py` to handle the inline keyboard responses
    - Catch storage exceptions, log error, reply STORAGE_ERROR
    - _Requirements: 2a.1, 2a.2, 2a.3, 2a.4, 5.2, 6.1_

  - [x] 4.4 Implement `cmd_roll` handler
    - Load list; guard empty (reply ROLL_EMPTY); call `random.choice`; reply ROLL_RESULT
    - Catch storage exceptions, log error, reply STORAGE_ERROR
    - _Requirements: 3.1, 3.2, 3.3, 6.1_

  - [ ]* 4.5 Write property test for roll result always from the list (Property 4)
    - **Property 4: Roll result is always from the list**
    - **Validates: Requirements 3.1**
    - For any non-empty list `L`, assert `random.choice(L) in L` holds for many iterations

  - [ ]* 4.6 Write property test for uniform random selection (Property 3)
    - **Property 3: Uniform random selection**
    - **Validates: Requirements 3.3**
    - Over a large number of rolls on a list of `k` items, assert each item frequency ≈ `1/k` within tolerance

  - [x] 4.7 Implement `cmd_list` handler
    - Load list; guard empty (reply LIST_EMPTY); format each entry using LIST_ITEM with `name`, `added_by`, and `added_at` (formatted in Asia/Taipei timezone); join lines and reply with LIST_HEADER
    - Catch storage exceptions, log error, reply STORAGE_ERROR
    - _Requirements: 4.1, 4.2, 6.1_

  - [x] 4.8 Implement `cmd_unknown` handler
    - Reply with HELP_TEXT for any unrecognised command or plain text
    - _Requirements: 6.2_

  - [x] 4.9 Write property test for invalid name rejection (Property 6)
    - **Property 6: Invalid name rejection**
    - **Validates: Requirements 1.6**
    - For any name containing `\n` or `/`, assert it is rejected and the list remains unchanged

- [ ] 5. Checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Create `main.py` entry point
  - [x] 6.1 Wire config → storage → bot handlers → `Application.run_polling()`
    - Import `config`, register all handlers from `bot.py` on the `Application`
    - Note: `CallbackQueryHandler` for `cmd_removeall` must be added once task 4.3a is complete
    - Configure `logging` to stdout (INFO level) so systemd/journald captures output
    - _Requirements: 8.1, 8.4_

- [x] 7. Create `requirements.txt` and `deploy/lunch-bot.service`
  - [x] 7.1 Write `requirements.txt`
    - Include `python-telegram-bot>=20.0` and `python-dotenv>=1.0`
    - _Requirements: 8.1_

  - [x] 7.2 Write `deploy/lunch-bot.service` systemd unit file
    - Set `After=network.target`, `Restart=on-failure`, `RestartSec=5`
    - Use `EnvironmentFile=/opt/lunch-bot/.env` for secrets
    - Include `[Install] WantedBy=multi-user.target` for auto-start on boot
    - _Requirements: 8.2, 8.3, 8.4, 8.5_

- [ ] 8. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Property tests use `hypothesis` (add to `requirements-dev.txt` as needed)
- Each task references specific requirements for traceability
- All user-facing strings must come from `messages.py`; no inline string literals in handlers

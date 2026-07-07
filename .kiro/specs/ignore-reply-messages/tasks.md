# Implementation Plan

## Overview

This plan fixes the spurious `HELP_TEXT` response the bot sends when a user replies to one of its
messages. It follows the bugfix methodology: first demonstrate the bug on unfixed code with an
exploratory bug-condition test, then apply a single early-return guard in `cmd_unknown`, and
finally verify the fix (fix-checking) and confirm existing behaviour is unchanged
(preservation-checking). Tests exercise `cmd_unknown` directly with a mock `Update` whose
`message.reply_text` is an `AsyncMock`, mirroring existing test conventions, and use Hypothesis
for property-based coverage. All test commands run via `.venv/bin/pytest`.

## Task Dependency Graph

```
1 (bug condition exploration test, FAILS on unfixed code)
2 (preservation tests, PASS on unfixed code)
        │
        ▼
3.1 (implement reply guard in cmd_unknown)
        │
        ├──► 3.2 (re-run task 1 test — now PASSES)
        └──► 3.3 (re-run task 2 tests — still PASS)
                        │
                        ▼
                4 (checkpoint — full suite passes)
```

Tasks 1 and 2 are independent and both precede the fix (3.1). Tasks 3.2 and 3.3 depend on 3.1.
Task 4 depends on 3.2 and 3.3.

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2"], "dependsOn": [] },
    { "wave": 2, "tasks": ["3.1"], "dependsOn": ["1", "2"] },
    { "wave": 3, "tasks": ["3.2", "3.3"], "dependsOn": ["3.1"] },
    { "wave": 4, "tasks": ["4"], "dependsOn": ["3.2", "3.3"] }
  ]
}
```

## Tasks

- [x] 1. Write bug condition exploration test (BEFORE implementing fix)
  - **Property 1: Bug Condition** - Reply messages to the catch-all are ignored
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - Create `tests/test_ignore_reply_messages.py`, mirroring `tests/test_select_roll.py` conventions: set `os.environ.setdefault("BOT_TOKEN", "test-token")` before `import bot`
  - Build a helper that constructs a mock `Update` whose `message.reply_to_message` is a truthy mock `Message` and whose `message.reply_text` is an `AsyncMock` (bug condition per design: `isBugCondition(input)` returns `input.message.reply_to_message IS NOT None`)
  - Write a Hypothesis property-based test: for arbitrary message text (both plain text and unknown-command strings like `/thanks`) with `reply_to_message` set, invoke `await bot.cmd_unknown(update, context)` and assert `update.message.reply_text` was NOT called (matches Expected Behavior / Property P in design: no response)
  - Include the two concrete counterexample cases from design: plain-text reply "sounds good" (Req 2.1) and unknown-command reply `/thanks` (Req 2.2)
  - Run test on UNFIXED code via `.venv/bin/pytest tests/test_ignore_reply_messages.py`
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - unfixed `cmd_unknown` calls `reply_text(HELP_TEXT)` even when `reply_to_message` is set)
  - Document counterexamples found (e.g., "cmd_unknown called reply_text with HELP_TEXT despite reply_to_message being set")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 2.1, 2.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-reply messages still receive HELP_TEXT
  - **IMPORTANT**: Follow observation-first methodology
  - Observe on UNFIXED code: with `reply_to_message = None`, `cmd_unknown` makes exactly one `reply_text(messages.HELP_TEXT)` call for both plain text and unknown-command messages
  - Reuse the mock `Update` helper from task 1, but with `message.reply_to_message = None` (cases where `isBugCondition` returns false)
  - Write a Hypothesis property-based test: for arbitrary message text (plain text and unknown-command strings) with `reply_to_message = None`, invoke `await bot.cmd_unknown(update, context)` and assert `update.message.reply_text` was called exactly once with `messages.HELP_TEXT` (Preservation Requirements from design)
  - Run tests on UNFIXED code via `.venv/bin/pytest tests/test_ignore_reply_messages.py`
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve for Req 3.1, 3.2)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2_

- [x] 3. Fix for spurious HELP_TEXT response on reply messages

  - [x] 3.1 Implement the reply guard in `cmd_unknown`
    - In `bot.py`, add an early-return guard at the top of `cmd_unknown`: `if update.message.reply_to_message is not None: return` before the `await update.message.reply_text(messages.HELP_TEXT)` call
    - Update the `cmd_unknown` docstring to note that it now ignores reply messages
    - Make NO changes to `main.py` — the catch-all `MessageHandler` registrations stay as they are
    - _Bug_Condition: isBugCondition(input) = input.message.reply_to_message IS NOT None (from design)_
    - _Expected_Behavior: cmd_unknown produces no response (does not call reply_text) when the message is a reply (from design)_
    - _Preservation: Non-reply plain text and unknown commands still receive exactly one reply_text(HELP_TEXT) call; recognised commands and the removeall callback are untouched (from design)_
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3, 3.4_

  - [x] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Reply messages to the catch-all are ignored
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior; when it passes, it confirms the fix is correct
    - Run via `.venv/bin/pytest tests/test_ignore_reply_messages.py`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — no `reply_text` call for reply messages)
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-reply messages still receive HELP_TEXT
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run via `.venv/bin/pytest tests/test_ignore_reply_messages.py`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — non-reply messages still get exactly one `reply_text(HELP_TEXT)` call)
    - Confirm all tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full suite via `.venv/bin/pytest` to confirm the fix introduces no regressions across existing tests (Req 3.3, 3.4)
  - Ensure all tests pass, ask the user if questions arise

## Notes

- The fix is a single early-return guard in `cmd_unknown` (`bot.py`); no changes to `main.py`.
- Property 1 (Bug Condition) MUST fail on unfixed code — that failure confirms the bug exists.
  Property 2 (Preservation) MUST pass on unfixed code — that establishes the baseline to preserve.
- Recognised commands (`/add`, `/remove`, `/removeall`, `/roll`, `/list`) and the `removeall`
  callback do not route through `cmd_unknown`, so they are unaffected by construction (Req 3.3, 3.4);
  task 4 confirms this via the full suite.
- All Python commands use the project venv (`.venv/bin/pytest`), per the workspace Python steering.

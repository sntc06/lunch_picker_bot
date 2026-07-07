# Ignore Reply Messages Bugfix Design

## Overview

The Lunch Bot wires two catch-all `MessageHandler`s in `main.py`, both routing to
`bot.cmd_unknown`:

- `MessageHandler(filters.COMMAND, bot.cmd_unknown)` — any unrecognised `/command`
- `MessageHandler(filters.TEXT & ~filters.COMMAND, bot.cmd_unknown)` — any plain text

`cmd_unknown` unconditionally replies with `HELP_TEXT`. The bug is that these handlers also
fire when a user *replies* to one of the bot's own messages (e.g. replying to the rolled
result). In Telegram such an update carries `update.message.reply_to_message`, but the handlers
do not distinguish replies from fresh messages, so the bot answers with the help text in the
middle of a conversation — noisy and unwanted.

The fix makes the bot ignore reply messages that would otherwise be handled by the catch-all
handlers, while leaving every other path untouched: non-reply plain text and unknown commands
still return `HELP_TEXT`, recognised commands (`/add`, `/remove`, `/removeall`, `/roll`, `/list`)
still work, and the `removeall` inline-keyboard callback still works.

Both catch-all handlers converge on the single function `cmd_unknown`, so a single guard at the
top of `cmd_unknown` covers both the plain-text and unknown-command cases. Placing the guard in
`cmd_unknown` (rather than in the `main.py` filter expressions) keeps the fix in one testable
location: `cmd_unknown` can be invoked directly in a unit/property test with a mock `Update`,
whereas the filter-registration path is bound to the running `Application` and is awkward to
exercise in isolation. This scopes the change to exactly the catch-all behaviour described in the
requirements — recognised commands are dispatched by their own `CommandHandler`s before the
catch-alls and are not affected.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — an incoming update reaches
  `cmd_unknown` (i.e. is plain text or an unrecognised command) **and** its message is a reply
  (`update.message.reply_to_message` is set).
- **Property (P)**: The desired behaviour under the bug condition — `cmd_unknown` produces no
  response (it does not call `update.message.reply_text`).
- **Preservation**: Existing behaviour that must remain unchanged — non-reply messages still get
  `HELP_TEXT` from `cmd_unknown`, recognised commands still run via their own handlers, and the
  `removeall` callback still runs.
- **cmd_unknown**: The handler in `bot.py` that both catch-all `MessageHandler`s route to; it
  currently always replies with `HELP_TEXT`.
- **reply_to_message**: The attribute on `update.message` (a `telegram.Message`) that is set to
  the replied-to `Message` when the incoming message is a reply, and `None` otherwise. This is the
  signal used to detect the bug condition.

## Bug Details

### Bug Condition

The bug manifests when a message that would fall through to the catch-all handlers is itself a
reply. Because both catch-all handlers route to `cmd_unknown`, and `cmd_unknown` replies with
`HELP_TEXT` regardless of whether the message is a reply, replying to the bot produces a spurious
help response.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type Update (routed to cmd_unknown — i.e. plain text OR unrecognised command)
  OUTPUT: boolean

  RETURN input.message.reply_to_message IS NOT None
END FUNCTION
```

Note: reaching `cmd_unknown` already implies the message is plain text or an unrecognised
command (recognised commands and the callback are dispatched earlier). The bug condition is
therefore fully characterised by the message being a reply.

### Examples

- **Plain-text reply (bug):** User replies to the bot's `🎲 今天去吃：Pasta House` message with
  "sounds good". Expected: no response. Actual (defect): bot replies with `HELP_TEXT`. (Req 1.1 →
  2.1)
- **Unknown-command reply (bug):** User replies to a bot message with `/thanks`. Expected: no
  response. Actual (defect): bot replies with `HELP_TEXT`. (Req 1.2 → 2.2)
- **Non-reply plain text (unchanged):** User sends "hello" as a fresh message. Expected and
  actual: bot replies with `HELP_TEXT`. (Req 3.1)
- **Non-reply unknown command (unchanged):** User sends `/foo` as a fresh message. Expected and
  actual: bot replies with `HELP_TEXT`. (Req 3.2)
- **Recognised command as a fresh message (unchanged):** `/roll` returns a rolled result. (Req 3.3)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Non-reply plain-text messages still receive `HELP_TEXT` (Req 3.1).
- Non-reply unrecognised commands still receive `HELP_TEXT` (Req 3.2).
- Recognised commands (`/add`, `/remove`, `/removeall`, `/roll`, `/list`) still process normally
  via their dedicated `CommandHandler`s (Req 3.3).
- The `removeall` inline-keyboard confirmation callback still processes normally via
  `CallbackQueryHandler` (Req 3.4).

**Scope:**
All inputs where the message is NOT a reply are completely unaffected by this fix. The fix only
suppresses the `HELP_TEXT` response for messages that both (a) reach `cmd_unknown` and (b) are
replies. Per the documented requirements scope, the fix targets the catch-all handlers only;
recognised commands and the callback are dispatched by their own handlers and are never gated by
the reply check — so a recognised command sent as a reply would still execute (out of scope for
this fix, and consistent with the requirements).

## Hypothesized Root Cause

Based on the bug description and the code in `bot.py` / `main.py`, the cause is well understood
(this is a missing-guard bug rather than a mystery):

1. **Missing reply check in `cmd_unknown`**: `cmd_unknown` unconditionally calls
   `update.message.reply_text(messages.HELP_TEXT)` with no inspection of
   `update.message.reply_to_message`. This is the primary and most likely single cause.

2. **Catch-all filters do not exclude replies**: The `MessageHandler` registrations in `main.py`
   (`filters.COMMAND` and `filters.TEXT & ~filters.COMMAND`) match reply messages just like fresh
   ones because neither filter includes `~filters.REPLY`. This is the same root cause viewed at
   the registration layer; fixing either layer resolves the bug.

3. **No distinction between conversational replies and commands**: The design never separated
   "user is talking about a bot message" from "user is issuing an instruction", so replies were
   never filtered out.

The chosen fix addresses cause (1) directly in `cmd_unknown`, which is the single convergence
point for both catch-all handlers and the most directly testable location.

## Correctness Properties

Property 1: Bug Condition - Reply messages to the catch-all are ignored

_For any_ update that reaches `cmd_unknown` (plain text or unrecognised command) where the bug
condition holds (`update.message.reply_to_message` is set, so `isBugCondition` returns true), the
fixed `cmd_unknown` SHALL produce no response — it SHALL NOT call `update.message.reply_text`, so
no `HELP_TEXT` (or any other message) is sent.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Non-reply messages still receive HELP_TEXT

_For any_ update that reaches `cmd_unknown` where the bug condition does NOT hold
(`update.message.reply_to_message` is `None`, so `isBugCondition` returns false), the fixed
`cmd_unknown` SHALL produce the same result as the original function — a single
`update.message.reply_text(HELP_TEXT)` call — preserving the existing help-text behaviour for
non-reply plain text and non-reply unrecognised commands.

**Validates: Requirements 3.1, 3.2**

## Fix Implementation

### Changes Required

Assuming the root cause analysis is correct, the fix is a single early-return guard in the
catch-all handler.

**File**: `bot.py`

**Function**: `cmd_unknown`

**Specific Changes**:
1. **Add a reply guard at the top of `cmd_unknown`**: Before sending `HELP_TEXT`, check whether
   the incoming message is a reply and return early if so.
   ```python
   async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
       """Handle any unrecognised command or plain text (ignore replies)."""
       if update.message.reply_to_message is not None:
           return
       await update.message.reply_text(messages.HELP_TEXT)
   ```

2. **No changes to `main.py` required**: The catch-all `MessageHandler` registrations stay as they
   are. (Alternative considered: add `& ~filters.REPLY` to both catch-all filters in `main.py`.
   This is idiomatic for python-telegram-bot but harder to unit-test in isolation, so it is not
   the chosen approach. It remains a valid equivalent fix if handler-level filtering is preferred
   later.)

3. **Docstring update**: Note that `cmd_unknown` now ignores replies, so the intent is explicit
   for future readers.

The recognised-command handlers, the `CallbackQueryHandler`, and all other code paths are left
untouched, satisfying the preservation requirements by construction.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that
demonstrate the bug on the unfixed code, then verify the fix works correctly and preserves
existing behaviour. Tests exercise `cmd_unknown` directly using a mock `Update` whose
`message.reply_text` is an async mock, so assertions can check whether (and with what)
`reply_text` was called — no live Telegram or network I/O is needed. This mirrors the existing
`select_roll` tests, which import `bot` after setting a dummy `BOT_TOKEN`.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm
or refute the root cause analysis (missing reply guard in `cmd_unknown`). If refuted, re-hypothesize.

**Test Plan**: Build a mock `Update` where `message.reply_to_message` is set to a truthy mock
`Message` and `message.reply_text` is an `AsyncMock`. Invoke `cmd_unknown` and assert that
`reply_text` was NOT called. Run this against the UNFIXED code to observe the failure (the unfixed
code calls `reply_text` with `HELP_TEXT`).

**Test Cases**:
1. **Plain-text reply**: `reply_to_message` set, message text is plain text → assert no
   `reply_text` call (will fail on unfixed code). (Req 2.1)
2. **Unknown-command reply**: `reply_to_message` set, message text is `/unknowncmd` → assert no
   `reply_text` call (will fail on unfixed code). (Req 2.2)

**Expected Counterexamples**:
- On unfixed code, `reply_text` is invoked with `messages.HELP_TEXT` even though
  `reply_to_message` is set.
- Confirms the root cause: `cmd_unknown` does not inspect `reply_to_message`.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces
the expected behavior (no response).

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO      # message.reply_to_message is set
  cmd_unknown_fixed(input)
  ASSERT reply_text was NOT called
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function
produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO  # message.reply_to_message is None
  ASSERT cmd_unknown_original(input) == cmd_unknown_fixed(input)
  # i.e. exactly one reply_text(HELP_TEXT) call in both cases
END FOR
```

**Testing Approach**: Property-based testing (Hypothesis, already a dev dependency) is recommended
for preservation checking because:
- It generates many message shapes automatically across the input domain (varied text, unknown
  command strings).
- It catches edge cases manual unit tests might miss.
- It provides strong assurance that non-reply behaviour is unchanged for the whole input space.

**Test Plan**: Observe on the UNFIXED code that non-reply messages produce exactly one
`reply_text(HELP_TEXT)` call, then write property-based tests that generate non-reply updates
(with `reply_to_message = None`) and assert the same single `HELP_TEXT` call after the fix.

**Test Cases**:
1. **Non-reply plain text preservation**: For generated plain-text messages with
   `reply_to_message = None`, assert exactly one `reply_text(HELP_TEXT)` call. (Req 3.1)
2. **Non-reply unknown command preservation**: For generated unknown-command messages with
   `reply_to_message = None`, assert exactly one `reply_text(HELP_TEXT)` call. (Req 3.2)
3. **Recognised command / callback preservation**: These do not route through `cmd_unknown`;
   integration-level checks (below) confirm their handlers remain registered and functional.

### Unit Tests

- `cmd_unknown` with `reply_to_message` set (plain text) → no `reply_text` call. (Req 2.1)
- `cmd_unknown` with `reply_to_message` set (unknown command text) → no `reply_text` call. (Req 2.2)
- `cmd_unknown` with `reply_to_message = None` (plain text) → one `reply_text(HELP_TEXT)` call. (Req 3.1)
- `cmd_unknown` with `reply_to_message = None` (unknown command) → one `reply_text(HELP_TEXT)` call. (Req 3.2)

### Property-Based Tests

- Generate non-reply updates (`reply_to_message = None`) with arbitrary message text and assert
  `cmd_unknown` always makes exactly one `reply_text(HELP_TEXT)` call (Property 2 / preservation).
- Generate reply updates (`reply_to_message` set) with arbitrary message text and assert
  `cmd_unknown` never calls `reply_text` (Property 1 / bug condition).

### Integration Tests

- Verify `main.py` still registers the `CommandHandler`s for `/add`, `/remove`, `/removeall`,
  `/roll`, `/list`, and the `CallbackQueryHandler` for `^removeall:` — the fix must not remove or
  reorder handler registration (Req 3.3, 3.4).
- Verify the two catch-all `MessageHandler`s remain registered so non-reply fall-through still
  reaches `cmd_unknown` (Req 3.1, 3.2).

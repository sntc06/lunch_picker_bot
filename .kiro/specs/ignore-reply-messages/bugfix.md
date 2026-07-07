# Bugfix Requirements Document

## Introduction

The Lunch Bot registers two catch-all message handlers that route to `cmd_unknown`:
`MessageHandler(filters.COMMAND, bot.cmd_unknown)` and
`MessageHandler(filters.TEXT & ~filters.COMMAND, bot.cmd_unknown)`. Both respond with
`HELP_TEXT` for any message that is not a recognised command.

The problem is that these handlers also fire when a user *replies* to one of the bot's own
messages (for example, replying to the rolled result). In Telegram, such an update carries a
`reply_to_message`. Because the handlers do not distinguish replies from fresh messages, a reply
is treated as an unknown command / plain text and the bot answers with the help text — an
unwanted, noisy response in the middle of a conversation.

This fix makes the bot ignore reply messages so that replying to the bot (e.g. to the rolled
result) no longer triggers a spurious help response.

## Bug Analysis

### Current Behavior (Defect)

When a user replies to an existing message (the incoming update's message has
`reply_to_message` set), the catch-all handlers still process it and respond with `HELP_TEXT`.

1.1 WHEN a user replies to a bot message (the message has `reply_to_message` set) with plain text THEN the system responds with `HELP_TEXT`
1.2 WHEN a user replies to a message (the message has `reply_to_message` set) with an unrecognised command THEN the system responds with `HELP_TEXT`

### Expected Behavior (Correct)

Reply messages that would otherwise be handled by the catch-all handlers are ignored — the bot
produces no response.

2.1 WHEN a user replies to a bot message (the message has `reply_to_message` set) with plain text THEN the system SHALL ignore the message and produce no response
2.2 WHEN a user replies to a message (the message has `reply_to_message` set) with an unrecognised command THEN the system SHALL ignore the message and produce no response

### Unchanged Behavior (Regression Prevention)

Non-reply messages (the common case) must behave exactly as before, and recognised commands must
keep working.

3.1 WHEN a plain-text message is received that is NOT a reply (`reply_to_message` is not set) THEN the system SHALL CONTINUE TO respond with `HELP_TEXT`
3.2 WHEN an unrecognised command is received that is NOT a reply (`reply_to_message` is not set) THEN the system SHALL CONTINUE TO respond with `HELP_TEXT`
3.3 WHEN a recognised command (`/add`, `/remove`, `/removeall`, `/roll`, `/list`) is received that is NOT a reply THEN the system SHALL CONTINUE TO process it normally
3.4 WHEN a `removeall` inline-keyboard confirmation callback is received THEN the system SHALL CONTINUE TO process it normally

# Requirements Document

## Introduction

A Telegram bot that helps users decide where to eat lunch by maintaining a personal list of restaurants and selecting one at random on demand. Users interact with the bot via slash commands: `/add` to register one or more restaurants, `/remove` to delete one, `/removeall` to clear the entire list, `/list` to view all entries, and `/roll` to get a random pick from the saved list.

## Glossary

- **Bot**: The Telegram bot application that receives and responds to user commands.
- **Restaurant**: A named entry representing a place to eat, stored in the restaurant list.
- **Restaurant_List**: The persistent collection of restaurants associated with a specific chat or user.
- **Command**: A Telegram slash command sent by the user to the Bot.
- **Service**: A Linux systemd unit that runs the Bot as a background daemon on the server.
- **Server**: The Ubuntu Linux machine hosting the Bot, operated via a text-only CLI environment.

## Requirements

### Requirement 1: Add a Restaurant

**User Story:** As a user, I want to add one or more restaurants to my list, so that they can be considered during random lunch selection.

#### Acceptance Criteria

1. WHEN a user sends `/add <restaurant_name>`, THE Bot SHALL add the restaurant to the user's Restaurant_List and confirm the addition with a success message.
2. WHEN a user sends `/add <name1> <name2> ...` with multiple space-separated names, THE Bot SHALL attempt to add each name individually and report per-name results (success or duplicate) in a single reply.
3. WHEN a user sends `/add <restaurant_name>` and the restaurant already exists in the Restaurant_List, THE Bot SHALL reject the addition and notify the user that the restaurant is already on the list.
4. WHEN a user sends `/add` without a restaurant name, THE Bot SHALL respond with a usage hint indicating the correct command format.
5. THE Bot SHALL store restaurant names in a case-insensitive manner to prevent duplicate entries that differ only by letter case.
6. WHEN a restaurant name contains a newline character (`\n`) or a forward slash (`/`), THE Bot SHALL reject that name and reply with a warning that the format is incorrect.

---

### Requirement 2: Remove a Restaurant

**User Story:** As a user, I want to remove a restaurant from my list, so that it is no longer considered during random lunch selection.

#### Acceptance Criteria

1. WHEN a user sends `/remove <restaurant_name>`, THE Bot SHALL remove the matching restaurant from the Restaurant_List and confirm the removal with a success message.
2. WHEN a user sends `/remove <restaurant_name>` and the restaurant does not exist in the Restaurant_List, THE Bot SHALL notify the user that the restaurant was not found.
3. WHEN a user sends `/remove` without a restaurant name, THE Bot SHALL respond with a usage hint indicating the correct command format.

---

### Requirement 2a: Remove All Restaurants

**User Story:** As a user, I want to clear my entire restaurant list at once, so that I can start fresh without removing entries one by one.

#### Acceptance Criteria

1. WHEN a user sends `/removeall`, THE Bot SHALL ask the user to confirm the action with a yes/no inline keyboard before proceeding.
2. WHEN the user confirms, THE Bot SHALL remove all entries from the Restaurant_List and reply with a success message.
3. WHEN the user cancels, THE Bot SHALL leave the Restaurant_List unchanged and reply with a cancellation message.
4. WHEN a user sends `/removeall` and the Restaurant_List is already empty, THE Bot SHALL notify the user that the list is already empty.

---

### Requirement 3: Roll for a Random Restaurant

**User Story:** As a user, I want to randomly select a restaurant from my list, so that I don't have to decide where to eat myself.

#### Acceptance Criteria

1. WHEN a user sends `/roll` and the Restaurant_List contains at least one restaurant, THE Bot SHALL select one restaurant uniformly at random and reply with the selected restaurant name.
2. WHEN a user sends `/roll` and the Restaurant_List is empty, THE Bot SHALL notify the user that the list is empty and suggest using `/add` to add restaurants first.
3. THE Bot SHALL ensure each restaurant in the Restaurant_List has an equal probability of being selected during a `/roll` command.

---

### Requirement 4: List Restaurants

**User Story:** As a user, I want to see all restaurants currently in my list, so that I know what options are available before rolling or making changes.

#### Acceptance Criteria

1. WHEN a user sends `/list` and the Restaurant_List contains at least one restaurant, THE Bot SHALL reply with a numbered list of all restaurants, where each entry shows the restaurant name, the Telegram username (or first name as fallback) of the user who added it, and the date/time it was added formatted in Taiwan local time (Asia/Taipei timezone).
2. WHEN a user sends `/list` and the Restaurant_List is empty, THE Bot SHALL notify the user that the list is empty and suggest using `/add` to add restaurants.

---

### Requirement 5: Persistent Storage

**User Story:** As a user, I want my restaurant list to be saved between sessions, so that I don't have to re-add restaurants every time I use the bot.

#### Acceptance Criteria

1. THE Bot SHALL persist the Restaurant_List so that it survives bot restarts.
2. WHEN a restaurant is added or removed, THE Bot SHALL immediately persist the updated Restaurant_List.

---

### Requirement 6: Error Handling

**User Story:** As a user, I want the bot to handle unexpected errors gracefully, so that it remains usable even when something goes wrong.

#### Acceptance Criteria

1. IF a storage operation fails, THEN THE Bot SHALL notify the user that the operation could not be completed and log the error details.
2. IF an unrecognized command is received, THEN THE Bot SHALL respond with a help message listing the available commands and their usage.

---

### Requirement 7: Localization (zh-TW)

**User Story:** As a user in Taiwan, I want all bot messages to be in Traditional Chinese, so that the bot is natural and readable for a Taiwanese audience.

#### Acceptance Criteria

1. THE Bot SHALL display all user-facing messages — including success confirmations, error messages, usage hints, help text, roll results, and list output — in Traditional Chinese as used in Taiwan (zh-TW).
2. THE Bot SHALL use Traditional Chinese characters (繁體中文) and SHALL NOT use Simplified Chinese characters (簡體中文) in any user-facing message.
3. THE Bot SHALL use Taiwan-region phrasing and conventions (e.g., 餐廳 for restaurant, 清單 for list) consistently across all messages.

---

### Requirement 8: Linux Service Deployment

**User Story:** As a server operator, I want to run the bot as a background service on Ubuntu Linux, so that it starts automatically and can be managed without a GUI.


#### Acceptance Criteria

1. THE Bot SHALL be executable as a background process on Ubuntu Linux without requiring a graphical user interface.
2. THE Bot SHALL support operation as a systemd Service so that it can be started, stopped, and restarted using standard `systemctl` commands.
3. THE Service SHALL be configurable to start automatically when the Server boots.
4. THE Bot SHALL write operational logs to a location accessible via standard CLI tools such as `journalctl` or a log file readable with `cat` or `tail`.
5. THE Bot SHALL read its configuration (including the Telegram bot token) from a file or environment variable so that secrets are not embedded in source code and can be managed via CLI on the Server.

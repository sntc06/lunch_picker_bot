# Requirements Document

## Introduction

A Telegram bot that helps users decide where to eat lunch by maintaining a personal list of restaurants and selecting one at random on demand. Users interact with the bot via slash commands: `/add` to register one or more restaurants, `/remove` to delete one, `/removeall` to clear the entire list, `/list` to view all entries, and `/roll` to get a random pick from the saved list.

To make repeated rolls feel more useful, the Bot supports a configurable behavior that avoids returning restaurants that were selected too recently in the same chat. This behavior is controlled by a persistent integer configuration setting, the No_Repeat_Window, that specifies how many of the most recent roll results are excluded from the next selection. The No_Repeat_Window is managed the same way as other configuration (such as the bot token and data file path) rather than through a runtime chat command: a value of 0 disables the behavior, a value of 1 excludes only the single immediately preceding result (the earlier block-once behavior), and larger values exclude a longer run of recent picks. The Bot remembers a bounded history of recent roll results for each chat on disk in the data folder, so the behavior continues to work after a restart, and degrades gracefully when excluding the recent window would otherwise leave no restaurant to pick (for example, when the list is small relative to the window).

## Glossary

- **Bot**: The Telegram bot application that receives and responds to user commands.
- **Restaurant**: A named entry representing a place to eat, stored in the restaurant list.
- **Restaurant_List**: The persistent collection of restaurants associated with a specific chat or user.
- **Command**: A Telegram slash command sent by the user to the Bot.
- **Roll**: A single execution of the `/roll` command that selects one Restaurant from the Restaurant_List.
- **No_Repeat_Window**: A non-negative integer configuration value that specifies how many of the most recent Roll results in a chat are excluded from selection on the next Roll. A value of 0 disables the behavior (every Roll selects from the entire Restaurant_List); a value of 1 excludes only the single most recent result (equivalent to the earlier block-once behavior); a value of N excludes up to the N most recent results. The No_Repeat_Window is read from configuration (environment variable or `.env` file) at startup, following the same mechanism used for other settings such as the Telegram bot token and data file path, defaults to 1 when not explicitly configured, remains constant for the duration of a Bot run, and is not changeable at runtime through chat commands.
- **Recent_Roll_History**: The ordered collection of the most recent Roll result names for a given chat, retained up to No_Repeat_Window entries with the most recent result last. The Recent_Roll_History is persisted durably on disk in the data folder so that it survives Bot restarts, and is tracked independently for each chat.
- **Eligible_Restaurants**: For a given Roll, the subset of the Restaurant_List that the Bot may select from after excluding restaurants named in the Recent_Roll_History, adjusted as needed so that at least one Eligible_Restaurant always remains when the Restaurant_List is non-empty.
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

### Requirement 3a: Avoid Recently Repeated Roll Results

**User Story:** As a user, I want `/roll` to avoid giving me a restaurant that was picked within the last few rolls, so that repeated rolls feel useful and varied instead of landing on the same choices too frequently.

#### Acceptance Criteria

1. THE No_Repeat_Window SHALL be an integer configuration value in the range 0 to 1000 inclusive, read from an environment variable or `.env` file at startup following the same configuration mechanism used for the Telegram bot token and data file path, and THE No_Repeat_Window SHALL default to 1 when not explicitly configured.
2. WHERE a legacy boolean-style value is configured for the No_Repeat_Window, THE Bot SHALL interpret a truthy value (`true`, `yes`, `on`, case-insensitive) as 1 and a falsy value (`false`, `no`, `off`, case-insensitive) as 0.
3. IF the configured No_Repeat_Window value cannot be interpreted as an integer in the range 0 to 1000 inclusive or as a supported boolean-style value, THEN THE Bot SHALL use the default No_Repeat_Window value of 1 and SHALL continue starting rather than failing to start.
4. THE Bot SHALL determine the No_Repeat_Window value solely from its persistent configuration at startup, and THE No_Repeat_Window value SHALL remain constant for the duration of a Bot run.
5. WHERE the No_Repeat_Window is 0, WHEN a user sends `/roll` and the Restaurant_List contains at least one restaurant, THE Bot SHALL select one restaurant uniformly at random from the entire Restaurant_List.
6. WHERE the No_Repeat_Window is 1 or greater, WHEN computing the Eligible_Restaurants for a Roll, THE Bot SHALL exclude from the Restaurant_List each restaurant whose name matches, case-insensitively, any of the most recent No_Repeat_Window entries of the Recent_Roll_History for that chat.
7. WHERE the No_Repeat_Window is 1 or greater, IF excluding the Recent_Roll_History would leave zero Eligible_Restaurants, THEN THE Bot SHALL retain the oldest excluded restaurants, dropping them from the exclusion one at a time from oldest to newest, until at least one Eligible_Restaurant remains.
8. WHERE the No_Repeat_Window is 1 or greater, WHEN a user sends `/roll` and the Restaurant_List contains at least one restaurant, THE Bot SHALL select the Roll result uniformly at random from the Eligible_Restaurants.
9. WHERE the No_Repeat_Window is 1 or greater, WHEN a user sends `/roll` and the Restaurant_List contains exactly one restaurant, THE Bot SHALL return that single restaurant as the Roll result.
10. WHERE the No_Repeat_Window is 1 or greater, WHEN a user sends `/roll` for a chat that has no Recent_Roll_History recorded because no Roll has ever produced a result for that chat, THE Bot SHALL select the result uniformly at random from the entire Restaurant_List.
11. WHERE the No_Repeat_Window is 1 or greater, IF a name in the Recent_Roll_History is no longer present in the Restaurant_List, THEN THE Bot SHALL exclude only the names that are currently present in the Restaurant_List and SHALL treat the absent name as excluding no restaurant.
12. WHEN a Roll returns a result, THE Bot SHALL append that result to the chat's Recent_Roll_History, retain only the most recent No_Repeat_Window entries, and persist the updated Recent_Roll_History to durable on-disk storage in the data folder.
13. WHEN the Bot starts, THE Bot SHALL load each chat's persisted Recent_Roll_History from on-disk storage so that the recent-repeat avoidance continues to apply after a Bot restart.
14. THE Bot SHALL track and persist the Recent_Roll_History independently for each chat so that Roll results in one chat do not affect Roll results in another chat.
15. WHEN selecting a Roll result, THE Bot SHALL complete the selection using at most one pass over the Restaurant_List plus at most No_Repeat_Window exclusion-relaxation steps, and SHALL NOT perform any unbounded or indefinite retry loop.
16. IF persisting the Recent_Roll_History to on-disk storage fails after a Roll, THEN THE Bot SHALL still deliver the Roll result to the user, SHALL retain the updated Recent_Roll_History in memory for the duration of the current Bot run, and SHALL log the failure.
17. IF a chat's persisted Recent_Roll_History cannot be read or parsed at startup, THEN THE Bot SHALL treat that chat's Recent_Roll_History as empty, SHALL continue starting, and SHALL log the failure.

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
3. THE Bot SHALL persist the Recent_Roll_History for each chat to durable on-disk storage in the data folder, in the same storage area as the Restaurant_List, so that the Recent_Roll_History survives Bot restarts.

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

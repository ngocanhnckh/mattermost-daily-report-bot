# Mattermost Scrum Bot

A Mattermost bot that helps teams manage daily scrum reports by sending reminders and collecting responses.

## Features

- Sends daily scrum report reminders Monday through Saturday
- Collects and stores user responses in a SQLite database
- Sends private message reminders to users who haven't submitted their daily report
- Supports excluding specific users (e.g., PMs, clients) from the daily report requirement
- Automatically tracks responses in message threads
- AI-powered report validation (Optional):
  - Validates report format and content using OpenRouter AI
  - Provides friendly, context-aware feedback to users
  - Flexible validation rules (allows "none" or "nothing" with explanation)
  - Uses GenZ-friendly communication style

## Setup

1. Create a bot account in Mattermost and get the bot token

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file with the following configuration:
   ```
   MATTERMOST_URL=your_mattermost_server_url
   BOT_TOKEN=your_bot_token
   BOT_USERNAME=your_bot_username
   EXCLUDED_USERS=user1,user2,user3
   
   # AI Validation Settings (Optional)
   AI_VALIDATION_ENABLED=true
   OPENROUTER_API_KEY=your_openrouter_api_key
   SITE_URL=your_site_url
   SITE_NAME=your_site_name
   ```

4. Create a `config.json` file:
   - Copy `config_example.json` to `config.json`
   - Customize the settings in `config.json`:
     ```json
     {
         "messages": {
             "daily_report": "Your daily report message template",
             "reminder": "Your reminder message template"
         },
         "schedule": {
             "report_time": "11:00",    // Time to send daily reports (24-hour format)
             "reminder_interval": 3,     // Hours between reminder messages
             "timezone": 7              // Timezone offset (e.g., 7 for GMT+7)
         }
     }
     ```
   - If `config.json` is not found, the bot will use default values from `config.py`

## AI Validation

The bot includes an optional AI validation feature that helps ensure daily reports follow the proper format and contain necessary information.

### Features
- Validates that reports include:
  1. Yesterday's accomplishments
  2. Today's planned tasks
  3. Any blockers or impediments (optional)
- Provides friendly, contextual feedback
- Supports bilingual responses (English/Vietnamese)
- Flexible validation rules:
  - Accepts "none" or "nothing" with proper explanation
  - Understands when blockers section can be skipped
  - Uses natural, GenZ-friendly language in responses

### Configuration
1. Get an API key from [OpenRouter](https://openrouter.ai/)
2. Set the following in your `.env` file:
   ```
   AI_VALIDATION_ENABLED=true
   OPENROUTER_API_KEY=your_api_key
   SITE_URL=your_site_url     # Optional: for OpenRouter rankings
   SITE_NAME=your_site_name   # Optional: for OpenRouter rankings
   ```

### Validation Response Examples
- Valid report feedback:
  ```
  "Thanks for the detailed report! You're all set for today! 🚀"
  ```
- Invalid report feedback:
  ```
  "Hey! Your report needs a bit more detail. Could you tell us what you're planning to work on today? Even if it's 'nothing', just let us know why! 😊"
  ```

## Running the Bot

```bash
python bot.py
```

The bot will:
1. Connect to your Mattermost server
2. Initialize AI validation if enabled
3. Send daily report requests at the configured time
4. Monitor message threads for responses
5. Validate responses and provide feedback
6. Send reminder DMs to users who haven't responded

## Database Schema

The bot stores daily reports in a SQLite database with the following schema:

```sql
CREATE TABLE daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    username TEXT NOT NULL,
    report_date DATE NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Contributing

Feel free to submit issues and enhancement requests! 
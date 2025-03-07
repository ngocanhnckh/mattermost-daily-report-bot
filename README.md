# Mattermost Scrum Bot

A Mattermost bot that helps teams manage daily scrum reports by sending reminders and collecting responses.

## Features

- Sends daily scrum report reminders Monday through Saturday
- Collects and stores user responses in a SQLite database
- Sends private message reminders to users who haven't submitted their daily report
- Supports excluding specific users (e.g., PMs, clients) from the daily report requirement
- Automatically tracks responses in message threads

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
   ```

4. Configure the bot settings in `config.py`:
   - `REPORT_TIME`: Time to send daily reports (24-hour format)
   - `REMINDER_INTERVAL`: Hours between reminder messages
   - Customize the report and reminder messages

## Running the Bot

```bash
python bot.py
```

The bot will:
1. Connect to your Mattermost server
2. Send daily report requests at the configured time
3. Monitor message threads for responses
4. Send reminder DMs to users who haven't responded

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
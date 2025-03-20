# Mattermost Scrum Bot

A Mattermost bot that helps teams manage daily scrum reports by sending reminders and collecting responses.

## Features

- Sends daily scrum report reminders Monday through Saturday
- Collects and stores user responses in a SQLite database
- Sends private message reminders to users who haven't submitted their daily report
- Supports excluding specific users (e.g., PMs, clients) from the daily report requirement
- Automatically tracks responses in message threads
- Web Interface for:
  - Viewing daily reports and statistics
  - Managing user and channel configurations
  - Managing excluded users list
  - Filtering reports by date, user, and channel
- AI-powered report validation (Optional):
  - Validates report format and content using OpenRouter AI
  - Provides friendly, context-aware feedback to users
  - Flexible validation rules (allows "none" or "nothing" with explanation)
  - Uses GenZ-friendly communication style
- SMS Reminders via Twilio (Optional):
  - Sends SMS reminders to users who haven't submitted reports
  - Customizable SMS message template
  - Supports phone numbers for each user
  - Configurable through web interface

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
   TEAM=yourteamnameinmattermost
   # AI Validation Settings (Optional)
   AI_VALIDATION_ENABLED=true
   OPENROUTER_API_KEY=your_openrouter_api_key
   SITE_URL=your_site_url
   SITE_NAME=your_site_name
   # Twilio Settings (Optional)
   TWILIO_ACCOUNT_SID=your_twilio_account_sid
   TWILIO_AUTH_TOKEN=your_twilio_auth_token
   TWILIO_FROM_NUMBER=your_twilio_phone_number
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
             "timezone": 7,             // Timezone offset (e.g., 7 for GMT+7)
             "report_deadline_time": "22:00"  // Deadline for submitting reports
         },
         "excluded_users": ["user1", "user2"],  // Users exempt from daily reports
         "users": {
             "mattermost_username": {
                 "jira_username": "jira.username",
                 "phone": "+1234567890",  // Required for SMS reminders
                 "bio": "Frontend Developer"
             }
         },
         "channels": {
             "mattermost-channel": {
                 "jira_project": "PROJ"
             }
         },
         "jira": {
             "url": "your_jira_instance_url",
             "token": "your_jira_api_token"
         },
         "twilio": {
             "enabled": true,
             "account_sid": "your_twilio_account_sid",
             "auth_token": "your_twilio_auth_token",
             "from_number": "+1234567890",
             "sms_template": "Hey {username}! Don't forget to submit your daily report in {channel_name}. Reply to the thread: {thread_link}"
         }
     }
     ```

## Web Interface

The bot includes a web interface for managing configurations and viewing reports:

### Features
- Daily Reports Dashboard:
  - View all daily reports in a sortable table
  - Filter reports by date, user, and channel
  - View submission statistics
  - Track submission rates and missed reports

- Configuration Management:
  - Manage user mappings (Mattermost to Jira usernames)
  - Configure channel to Jira project mappings
  - Manage excluded users list
  - Configure Twilio SMS settings
  - All changes are saved automatically to config.json

### Access
1. Start the web server:
   ```bash
   python web_server.py
   ```
2. Open your browser and navigate to:
   ```
   http://localhost:5001
   ```
3. Use the navigation menu to switch between:
   - Daily Reports: View and filter reports
   - Configuration: Manage user and channel settings

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

## Jira Integration

The bot now includes powerful Jira integration features that help teams manage their sprint tasks more effectively.

### Features
- Automatically validates and updates sprint tasks:
  - Sets missing start/end dates
  - Assigns unassigned tasks
  - Adds original time estimates
  - AI-powered task analysis for smart assignments and estimates
- Shows active tasks in daily reports
- Tracks task updates and progress
- Provides AI reasoning for each task update decision
- Sends urgent task reminders

### Configuration
Add Jira settings to your `config.json`:

```json
{
    "jira": {
        "url": "your_jira_instance_url",
        "token": "your_jira_api_token"  // Get from Atlassian Account Settings
    },
    "users": {
        "mattermost_username": {
            "jira_username": "jira.username",
            "phone": "+1234567890",  // Optional
            "bio": "Frontend Developer"  // Used for AI task assignment
        }
    },
    "channels": {
        "mattermost-channel": {
            "jira_project": "PROJ"  // Your Jira project code
        }
    }
}
```

### Custom Field Configuration
The bot automatically detects and uses your Jira custom fields for:
- Start date
- End date
Recommended to use with Jira plugin BigGantt or BigPicture to have these fields built in and use with Ganttchart

No manual configuration needed - the bot will automatically detect these fields during initialization by looking for:
- A field named "Start date"
- A field named "End date"
- The built-in timetracking field for Original Estimate

### AI Task Management
The bot uses AI to:
1. Analyze task descriptions and requirements
2. Suggest appropriate assignees based on:
   - Team member roles/expertise (from their bio)
   - Current workload
   - Task type (frontend/backend/AI)
3. Estimate completion time based on:
   - Task complexity
   - Similar past tasks
   - Sprint timeline
4. Set realistic start/end dates considering:
   - Sprint schedule
   - Task dependencies
   - Team capacity

### Task Update Messages
The bot will send updates like:

## Running the Bot and viewer

```bash
python bot.py
python web_server.py
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
import os
import json
from dotenv import load_dotenv
from datetime import timezone, timedelta
from functools import lru_cache

load_dotenv()

def load_config_json():
    """Load configuration from config.json with fallback values."""
    try:
        with open('config.json', 'r') as f:
            config_json = json.load(f)
            return config_json
    except FileNotFoundError:
        return {
            'messages': {
                'daily_report': """
Please reply to this thread with your daily report including:
1. What did you accomplish yesterday?
2. What are you planning to do today?
3. Any blockers or challenges?
""",
                'reminder': """
Hey bro, it seems you missed the daily report today, please submit your report as soon as possible. \n
Even if you have done nothing, it's ok to report. \n
Failure to report will affect your work performance and affect the whole team, please be advised! \n
Let's do it together! \n
""",
                'remind_task': "Một chút cập nhật nào, please update these tasks: \n"
            },
            'schedule': {
                'report_time': "16:56",
                'reminder_interval': 0.01,
                'timezone': 7,
                'report_deadline_time': "17:00"
            },
            'users': {},
            'channels': {},
            'jira': {
                'url': os.getenv('JIRA_URL', ''),
                'token': os.getenv('JIRA_TOKEN', '')
            },
            'twilio': {
                'enabled': False,
                'account_sid': os.getenv('TWILIO_ACCOUNT_SID', ''),
                'auth_token': os.getenv('TWILIO_AUTH_TOKEN', ''),
                'from_number': os.getenv('TWILIO_FROM_NUMBER', ''),
                'sms_template': "Hey {username}! Don't forget to submit your daily report in {channel_name}. Reply to the thread: {thread_link}"
            }
        }

# Load base configuration
config_json = load_config_json()

# Messages and schedule settings
DAILY_REPORT_MESSAGE = config_json['messages']['daily_report']
REMIND_TASK_MESSAGE = config_json['messages']['remind_task']
REPORT_TIME = config_json['schedule']['report_time']
REMINDER_INTERVAL = config_json['schedule']['reminder_interval']
TIMEZONE = timezone(timedelta(hours=config_json['schedule']['timezone']))
REPORT_DEADLINE_TIME = config_json['schedule'].get('report_deadline_time', '17:00')

def get_user_mappings():
    """Get user mappings from config.json, reloading on each call."""
    config = load_config_json()
    return config.get('users', {})

def get_channel_mappings():
    """Get channel mappings from config.json, reloading on each call."""
    config = load_config_json()
    return config.get('channels', {})

# Mattermost Configuration
MATTERMOST_URL = os.getenv('MATTERMOST_URL', 'http://localhost:8065')
BOT_TOKEN = os.getenv('BOT_TOKEN')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'scrum-bot')
TEAM_NAME = os.getenv('TEAM_NAME', '')

# User Configuration
def get_excluded_users():
    """Get excluded users from config.json, reloading on each call."""
    config = load_config_json()
    return config.get('excluded_users', [])

# Database Configuration
DB_PATH = 'daily_reports.db'

# AI Validation Settings
AI_VALIDATION_ENABLED = os.getenv('AI_VALIDATION_ENABLED', 'true').lower() == 'true'
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
SITE_URL = os.getenv('SITE_URL', '')
SITE_NAME = os.getenv('SITE_NAME', '')

# Jira Configuration
JIRA_URL = config_json.get('jira', {}).get('url', os.getenv('JIRA_URL'))
JIRA_TOKEN = config_json.get('jira', {}).get('token', os.getenv('JIRA_TOKEN'))

# Twilio Configuration
TWILIO_ENABLED = config_json.get('twilio', {}).get('enabled', False)
TWILIO_ACCOUNT_SID = config_json.get('twilio', {}).get('account_sid', os.getenv('TWILIO_ACCOUNT_SID'))
TWILIO_AUTH_TOKEN = config_json.get('twilio', {}).get('auth_token', os.getenv('TWILIO_AUTH_TOKEN'))
TWILIO_FROM_NUMBER = config_json.get('twilio', {}).get('from_number', os.getenv('TWILIO_FROM_NUMBER'))
TWILIO_SMS_TEMPLATE = config_json.get('twilio', {}).get('sms_template', "Hey {username}! Don't forget to submit your daily report in {channel_name}. Reply to the thread: {thread_link}") 
import os
from dotenv import load_dotenv
from datetime import timezone, timedelta

load_dotenv()

# Mattermost Configuration
MATTERMOST_URL = os.getenv('MATTERMOST_URL', 'http://localhost:8065')
BOT_TOKEN = os.getenv('BOT_TOKEN')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'scrum-bot')

# Daily Report Configuration
TIMEZONE = timezone(timedelta(hours=7))  # GMT+7
REPORT_TIME = "11:00"  # 24-hour format in GMT+7
REMINDER_INTERVAL = 3  # hours
EXCLUDED_USERS = os.getenv('EXCLUDED_USERS', '').split(',')

# Database Configuration
DB_PATH = 'daily_reports.db'

# Messages
DAILY_REPORT_MESSAGE = """
Please reply to this thread with your daily report including:
1. What did you accomplish yesterday?
2. What are you planning to do today?
3. Any blockers or challenges?
"""

REMINDER_MESSAGE = """
Hey bro, it seems you missed the daily report today, please submit your report as soon as possible. \n
Even if you have done nothing, it's ok to report. \n
Failure to report will affect your work performance and affect the whole team, please be advised! \n
Let's do it together! \n
""" 
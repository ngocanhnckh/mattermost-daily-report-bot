import sqlite3
from datetime import datetime
from config import DB_PATH
import json

class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # First create tables with new column
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    channel_name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    report_date DATE NOT NULL,
                    message TEXT NOT NULL,
                    is_ai_generated BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Safely add column if it doesn't exist (SQLite specific approach)
            try:
                cursor.execute('ALTER TABLE daily_reports ADD COLUMN is_ai_generated BOOLEAN DEFAULT 0')
            except sqlite3.OperationalError as e:
                if 'duplicate column name' not in str(e).lower():
                    raise e
            
            # Your existing bot_report_requests table creation
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_report_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    channel_name TEXT NOT NULL,
                    request_date DATE NOT NULL,
                    requested_users TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

             # Add reminders table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    reminder_time TEXT NOT NULL,  -- ISO format string
                    message TEXT NOT NULL
                )
            ''')
            conn.commit()

    def add_report(self, channel_id, channel_name, username, message, is_ai_generated=False):
        """Add a report to the database.
        
        Args:
            channel_id (str): The channel ID
            channel_name (str): The channel name
            username (str): The username
            message (str): The report message
            is_ai_generated (bool, optional): Whether this is an AI generated report
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            today = datetime.now().date()
            cursor.execute('''
                INSERT INTO daily_reports 
                (channel_id, channel_name, username, report_date, message, is_ai_generated)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (channel_id, channel_name, username, today, message, is_ai_generated))
            conn.commit()

    def add_bot_request(self, channel_id, channel_name, requested_users):
        """Record when the bot requests reports from users in a channel."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            today = datetime.now().date()
            # Convert list of usernames to JSON string
            users_json = json.dumps(requested_users)
            cursor.execute('''
                INSERT INTO bot_report_requests (channel_id, channel_name, request_date, requested_users)
                VALUES (?, ?, ?, ?)
            ''', (channel_id, channel_name, today, users_json))
            conn.commit()

    def get_today_reports(self, channel_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            today = datetime.now().date()
            cursor.execute('''
                SELECT username FROM daily_reports
                WHERE channel_id = ? AND report_date = ?
            ''', (channel_id, today))
            return [row[0] for row in cursor.fetchall()]

    def add_reminder(self, channel_id, username, reminder_time, message):
        """Add a custom reminder to the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO reminders (channel_id, username, reminder_time, message)
                VALUES (?, ?, ?, ?)
            ''', (channel_id, username, reminder_time, message))
            conn.commit()

    def get_due_reminders(self, now_iso):
        """Fetch reminders that are due (reminder_time <= now)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, channel_id, username, reminder_time, message
                FROM reminders
                WHERE reminder_time <= ?
            ''', (now_iso,))
            return cursor.fetchall()

    def remove_reminder(self, reminder_id):
        """Remove a reminder after it is sent."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM reminders WHERE id = ?', (reminder_id,))
            conn.commit()

    def has_reported_today(self, channel_id, username):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            today = datetime.now().date()
            cursor.execute('''
                SELECT COUNT(*) FROM daily_reports
                WHERE channel_id = ? AND username = ? AND report_date = ?
            ''', (channel_id, username, today))
            return cursor.fetchone()[0] > 0 
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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    channel_name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    report_date DATE NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_report_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    channel_name TEXT NOT NULL,
                    request_date DATE NOT NULL,
                    requested_users TEXT NOT NULL,  -- JSON array of usernames
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def add_report(self, channel_id, channel_name, username, message):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            today = datetime.now().date()
            cursor.execute('''
                INSERT INTO daily_reports (channel_id, channel_name, username, report_date, message)
                VALUES (?, ?, ?, ?, ?)
            ''', (channel_id, channel_name, username, today, message))
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

    def has_reported_today(self, channel_id, username):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            today = datetime.now().date()
            cursor.execute('''
                SELECT COUNT(*) FROM daily_reports
                WHERE channel_id = ? AND username = ? AND report_date = ?
            ''', (channel_id, username, today))
            return cursor.fetchone()[0] > 0 
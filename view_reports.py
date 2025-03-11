import sqlite3
from datetime import datetime, timedelta
import calendar
import argparse
from tabulate import tabulate
from collections import defaultdict
import json

def get_working_days(year, month):
    """Get the number of working days (Monday-Saturday) up to current date for current month,
    or all working days for past months."""
    c = calendar.Calendar()
    working_days = 0
    current_date = datetime.now().date()
    
    for date in c.itermonthdates(year, month):
        # Skip dates not in the target month
        if date.month != month:
            continue
            
        # For current month, only count days up to today
        if year == current_date.year and month == current_date.month and date > current_date:
            continue
            
        # Count Monday(0) to Saturday(5)
        if date.weekday() < 6:
            working_days += 1
            
    return working_days

def get_monthly_reports(db_path, year, month):
    """Get all reports and statistics for the specified month."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get start and end date for the month
    start_date = datetime(year, month, 1).strftime('%Y-%m-%d')
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)
    end_date = end_date.strftime('%Y-%m-%d')

    # Get all reports for the month including channel information
    cursor.execute("""
        SELECT username, report_date, message, channel_id, channel_name
        FROM daily_reports 
        WHERE report_date BETWEEN ? AND ?
        ORDER BY report_date, username
    """, (start_date, end_date))
    reports = cursor.fetchall()

    # Get all bot report requests for the month
    cursor.execute("""
        SELECT channel_id, channel_name, request_date, requested_users
        FROM bot_report_requests 
        WHERE request_date BETWEEN ? AND ?
    """, (start_date, end_date))
    bot_requests = cursor.fetchall()

    # Process bot requests into a structure tracking which users were requested on which days
    channel_requests = {}  # {channel_id: {name: str, dates: {date: set(usernames)}}}
    for channel_id, channel_name, request_date, requested_users_json in bot_requests:
        if channel_id not in channel_requests:
            channel_requests[channel_id] = {'name': channel_name, 'dates': {}}
        
        # Parse the JSON array of requested users
        requested_users = json.loads(requested_users_json)
        channel_requests[channel_id]['dates'][request_date] = set(requested_users)

    conn.close()
    return reports, channel_requests

def analyze_reports(reports, channel_requests, year, month):
    """Analyze reports and generate statistics."""
    user_reports = defaultdict(lambda: defaultdict(list))  # {username: {channel_id: [(date, message)]}}
    all_users = set()  # Track all users who were requested to report
    
    # Organize reports by user and channel
    for username, date, message, channel_id, channel_name in reports:
        user_reports[username][channel_id].append((date, message))

    # Get all users who were requested to report
    for channel_id, channel_info in channel_requests.items():
        for date_users in channel_info['dates'].values():
            all_users.update(date_users)

    # Calculate statistics
    stats = []
    for username in all_users:
        total_submitted = 0
        total_expected = 0
        channel_stats = []

        # Check each channel where the user was requested to report
        for channel_id, channel_info in channel_requests.items():
            channel_name = channel_info['name']
            
            # Count days when this user was expected to report in this channel
            expected = sum(1 for date_users in channel_info['dates'].values() 
                         if username in date_users)
            
            if expected > 0:  # Only process channels where the user was requested
                # Count submitted reports for this channel
                submitted = len(user_reports[username][channel_id])
                total_submitted += submitted
                total_expected += expected
                
                # Add channel statistics
                channel_stats.append(f"{channel_name}: {submitted}/{expected}")

        # Calculate overall statistics
        missed_reports = total_expected - total_submitted if total_expected > 0 else 0
        submission_rate = (total_submitted / total_expected * 100) if total_expected > 0 else 0
        
        stats.append([
            username,
            total_submitted,
            missed_reports,
            f"{submission_rate:.1f}%",
            ", ".join(channel_stats) if channel_stats else "No reports requested"
        ])

    return sorted(stats, key=lambda x: x[0])  # Sort by username

def display_reports(reports, stats, year, month):
    """Display the reports and statistics in a formatted way."""
    month_name = calendar.month_name[month]
    working_days = get_working_days(year, month)

    print(f"\n=== Report Statistics for {month_name} {year} ===")
    print(f"Working Days (Mon-Sat): {working_days}\n")

    # Display statistics
    print("Report Submission Statistics:")
    headers = ["Username", "Reports Submitted", "Reports Missed", "Submission Rate", "Channel Breakdown"]
    print(tabulate(stats, headers=headers, tablefmt="grid"))

    # Display detailed reports
    print(f"\nDetailed Reports for {month_name} {year}:")
    current_date = None
    for username, date, message, channel_id, channel_name in sorted(reports, key=lambda x: (x[1], x[0])):
        if date != current_date:
            print(f"\n[{date}]")
            current_date = date
        print(f"- {username} ({channel_name}):")
        for line in message.split('\n'):
            print(f"  {line}")

def main():
    parser = argparse.ArgumentParser(description='View daily reports from database')
    parser.add_argument('--month', type=int, default=datetime.now().month,
                      help='Month number (1-12)')
    parser.add_argument('--year', type=int, default=datetime.now().year,
                      help='Year (YYYY)')
    parser.add_argument('--db', type=str, default='daily_reports.db',
                      help='Path to the database file')
    
    args = parser.parse_args()

    try:
        reports, channel_requests = get_monthly_reports(args.db, args.year, args.month)
        stats = analyze_reports(reports, channel_requests, args.year, args.month)
        display_reports(reports, stats, args.year, args.month)
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main() 
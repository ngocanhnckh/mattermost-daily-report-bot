import sqlite3
from datetime import datetime, timedelta
import calendar
import argparse
from tabulate import tabulate
from collections import defaultdict

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

    # Get all unique users and their channels for this period
    cursor.execute("""
        SELECT DISTINCT username, channel_id, channel_name
        FROM daily_reports 
        WHERE report_date BETWEEN ? AND ?
    """, (start_date, end_date))
    user_channels = cursor.fetchall()

    # Process users and their channels
    users = {}  # Dictionary to store users and their channels
    for username, channel_id, channel_name in user_channels:
        if username not in users:
            users[username] = set()
        users[username].add(channel_id)

    conn.close()
    return reports, users

def analyze_reports(reports, users, year, month):
    """Analyze reports and generate statistics."""
    working_days = get_working_days(year, month)
    user_reports = defaultdict(lambda: defaultdict(int))  # Track reports per user per channel
    user_channel_names = defaultdict(dict)  # Track channel names for each user
    
    # Count reports per user per channel and store channel names
    for username, date, message, channel_id, channel_name in reports:
        user_reports[username][channel_id] += 1
        user_channel_names[username][channel_id] = channel_name

    # Calculate statistics
    stats = []
    for username, channels in users.items():
        num_channels = len(channels)
        total_expected_reports = working_days * num_channels
        total_submitted = sum(user_reports[username].values())
        missed_reports = total_expected_reports - total_submitted
        submission_rate = (total_submitted / total_expected_reports) * 100 if total_expected_reports > 0 else 0
        
        # Format channel information
        channel_info = [
            f"{user_channel_names[username].get(ch_id, 'Unknown')}: {user_reports[username][ch_id]}/{working_days}"
            for ch_id in channels
        ]
        
        stats.append([
            username,
            total_submitted,
            missed_reports,
            f"{submission_rate:.1f}%",
            ", ".join(channel_info)  # Add channel breakdown
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
        reports, users = get_monthly_reports(args.db, args.year, args.month)
        stats = analyze_reports(reports, users, args.year, args.month)
        display_reports(reports, stats, args.year, args.month)
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main() 
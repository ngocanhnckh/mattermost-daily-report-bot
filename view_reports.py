import sqlite3
from datetime import datetime, timedelta
import calendar
import argparse
from tabulate import tabulate
from collections import defaultdict

def get_working_days(year, month):
    """Get the number of working days (Monday-Saturday) in the given month."""
    c = calendar.Calendar()
    working_days = 0
    for date in c.itermonthdates(year, month):
        if date.month == month and date.weekday() < 6:  # Monday(0) to Saturday(5)
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

    # Get all reports for the month
    cursor.execute("""
        SELECT username, report_date, message 
        FROM daily_reports 
        WHERE report_date BETWEEN ? AND ?
        ORDER BY report_date, username
    """, (start_date, end_date))
    reports = cursor.fetchall()

    # Get unique users who have reported at least once
    cursor.execute("""
        SELECT DISTINCT username 
        FROM daily_reports 
        WHERE report_date BETWEEN ? AND ?
    """, (start_date, end_date))
    users = [user[0] for user in cursor.fetchall()]

    conn.close()
    return reports, users

def analyze_reports(reports, users, year, month):
    """Analyze reports and generate statistics."""
    working_days = get_working_days(year, month)
    user_reports = defaultdict(list)
    
    # Organize reports by user
    for username, date, message in reports:
        user_reports[username].append((date, message))

    # Calculate statistics
    stats = []
    for user in sorted(users):
        reports_submitted = len(user_reports[user])
        missed_reports = working_days - reports_submitted
        submission_rate = (reports_submitted / working_days) * 100 if working_days > 0 else 0
        stats.append([
            user,
            reports_submitted,
            missed_reports,
            f"{submission_rate:.1f}%"
        ])

    return stats

def display_reports(reports, stats, year, month):
    """Display the reports and statistics in a formatted way."""
    month_name = calendar.month_name[month]
    working_days = get_working_days(year, month)

    print(f"\n=== Report Statistics for {month_name} {year} ===")
    print(f"Working Days (Mon-Sat): {working_days}\n")

    # Display statistics
    print("Report Submission Statistics:")
    headers = ["Username", "Reports Submitted", "Reports Missed", "Submission Rate"]
    print(tabulate(stats, headers=headers, tablefmt="grid"))

    # Display detailed reports
    print(f"\nDetailed Reports for {month_name} {year}:")
    current_date = None
    for username, date, message in sorted(reports, key=lambda x: (x[1], x[0])):
        if date != current_date:
            print(f"\n[{date}]")
            current_date = date
        print(f"- {username}:")
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
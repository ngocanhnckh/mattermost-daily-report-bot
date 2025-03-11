from flask import Flask, render_template, jsonify, request
from datetime import datetime
import calendar
from database import Database
from view_reports import get_monthly_reports, analyze_reports
import os

app = Flask(__name__)
db = Database()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/reports')
def get_reports():
    # Get query parameters
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    date = request.args.get('date', None)  # Optional date filter in YYYY-MM-DD format
    username = request.args.get('username', None)  # Optional username filter
    channel = request.args.get('channel', None)  # Optional channel filter
    
    # Reuse existing report gathering logic
    reports, channel_requests = get_monthly_reports(db.db_path, year, month)
    
    # Get all unique users and channels from bot requests
    all_users = set()
    all_channels = set()
    for channel_id, channel_info in channel_requests.items():
        all_channels.add(channel_info['name'])
        for date_users in channel_info['dates'].values():
            all_users.update(date_users)
    
    # Apply filters
    if date:
        reports = [r for r in reports if r[1] == date]
    if username:
        reports = [r for r in reports if r[0] == username]
    if channel:
        reports = [r for r in reports if r[4] == channel]  # channel_name is at index 4
    
    stats = analyze_reports(reports, channel_requests, year, month)
    
    return jsonify({
        'reports': [
            {
                'username': report[0],
                'date': report[1],
                'message': report[2],
                'channel_id': report[3],
                'channel_name': report[4]
            }
            for report in reports
        ],
        'statistics': [
            {
                'username': stat[0],
                'submitted': stat[1],
                'missed': stat[2],
                'rate': stat[3],
                'channels': stat[4]
            }
            for stat in stats
        ],
        'filters': {
            'channels': sorted(all_channels),
            'usernames': sorted(all_users)
        }
    })

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)

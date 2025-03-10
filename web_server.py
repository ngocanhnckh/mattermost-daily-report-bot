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
    
    # Reuse existing report gathering logic
    reports, users = get_monthly_reports(db.db_path, year, month)
    stats = analyze_reports(reports, users, year, month)
    
    return jsonify({
        'reports': [
            {
                'username': username,
                'date': date,
                'message': message
            }
            for username, date, message in reports
        ],
        'statistics': [
            {
                'username': stat[0],
                'submitted': stat[1],
                'missed': stat[2],
                'rate': stat[3]
            }
            for stat in stats
        ]
    })

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)

from flask import Flask, render_template, jsonify, request
from datetime import datetime
import calendar
from database import Database
from view_reports import get_monthly_reports, analyze_reports
import os
import json
from config import load_config_json, get_user_mappings, get_channel_mappings

app = Flask(__name__)
db = Database()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/config')
def config_page():
    return render_template('config.html')

@app.route('/api/config')
def get_config():
    """Get current configuration."""
    config = load_config_json()
    return jsonify({
        'users': get_user_mappings(),
        'channels': get_channel_mappings(),
        'excluded_users': config.get('excluded_users', [])
    })

@app.route('/api/config/users/<username>', methods=['GET'])
def get_user(username):
    """Get user configuration."""
    users = get_user_mappings()
    if username in users:
        return jsonify(users[username])
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/config/channels/<name>', methods=['GET'])
def get_channel(name):
    """Get channel configuration."""
    channels = get_channel_mappings()
    if name in channels:
        return jsonify(channels[name])
    return jsonify({'error': 'Channel not found'}), 404

@app.route('/api/config/users/<username>', methods=['POST'])
def update_user(username):
    """Update or create user configuration."""
    try:
        data = request.get_json()
        config = load_config_json()
        
        # Update user configuration
        if 'users' not in config:
            config['users'] = {}
        config['users'][username] = data
        
        # Save to file
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config/channels/<name>', methods=['POST'])
def update_channel(name):
    """Update or create channel configuration."""
    try:
        data = request.get_json()
        config = load_config_json()
        
        # Update channel configuration
        if 'channels' not in config:
            config['channels'] = {}
        config['channels'][name] = data
        
        # Save to file
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config/users/<username>', methods=['DELETE'])
def delete_user(username):
    """Delete user configuration."""
    try:
        config = load_config_json()
        
        # Remove user if exists
        if 'users' in config and username in config['users']:
            del config['users'][username]
            
            # Save to file
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
                
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'User not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config/channels/<name>', methods=['DELETE'])
def delete_channel(name):
    """Delete channel configuration."""
    try:
        config = load_config_json()
        
        # Remove channel if exists
        if 'channels' in config and name in config['channels']:
            del config['channels'][name]
            
            # Save to file
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
                
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Channel not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

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

@app.route('/api/config/excluded-users', methods=['POST'])
def add_excluded_user():
    """Add a user to the excluded users list."""
    try:
        data = request.get_json()
        username = data.get('username')
        
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'}), 400
            
        config = load_config_json()
        
        # Initialize excluded_users if it doesn't exist
        if 'excluded_users' not in config:
            config['excluded_users'] = []
            
        # Add username if not already in the list
        if username not in config['excluded_users']:
            config['excluded_users'].append(username)
            
            # Save to file
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
                
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'User is already in the excluded list'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config/excluded-users/<username>', methods=['DELETE'])
def delete_excluded_user(username):
    """Remove a user from the excluded users list."""
    try:
        config = load_config_json()
        
        # Check if excluded_users exists and username is in the list
        if 'excluded_users' in config and username in config['excluded_users']:
            config['excluded_users'].remove(username)
            
            # Save to file
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
                
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'User not found in excluded list'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config/twilio', methods=['GET'])
def get_twilio_config():
    """Get Twilio configuration."""
    config = load_config_json()
    return jsonify(config.get('twilio', {}))

@app.route('/api/config/twilio', methods=['POST'])
def update_twilio_config():
    """Update Twilio configuration."""
    try:
        data = request.get_json()
        config = load_config_json()
        
        # Update Twilio configuration
        if 'twilio' not in config:
            config['twilio'] = {}
        config['twilio'].update(data)
        
        # Save to file
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)

import time
import schedule
from datetime import datetime, timedelta
from threading import Thread
from mattermostdriver import Driver
from database import Database
from config import (
    MATTERMOST_URL, BOT_TOKEN, BOT_USERNAME,
    REPORT_TIME, REMINDER_INTERVAL, EXCLUDED_USERS,
    DAILY_REPORT_MESSAGE, REMINDER_MESSAGE, TIMEZONE
)
import ssl
from urllib.parse import urlparse
import json
import asyncio

class ScrumBot:
    def __init__(self):
        base_url = MATTERMOST_URL.split(':8065')[0].replace('http://', '')
        
        self.driver = Driver({
            'url': base_url,
            'token': BOT_TOKEN,
            'basepath': '/api/v4',
            'port': 8065,
            'scheme': 'http'
        })
        self.db = Database()
        self.channels = {}
        self.pending_reminders = {}

    def start(self):
        print("Bot started")
        self.driver.login()
        self.bot_id = self.driver.users.get_user_by_username(BOT_USERNAME)['id']
        
        # Initialize channels the bot is a member of
        print("\n=== Initializing channels ===")
        try:
            # First get the team memberships for the bot
            print("Getting team memberships for bot...")
            team_memberships = self.driver.teams.get_team_members_for_user('me')
            print(f"Found {len(team_memberships)} team memberships:")
            
            for team_member in team_memberships:
                team_id = team_member['team_id']
                try:
                    # Get team details
                    team = self.driver.teams.get_team(team_id)
                    print(f"\nTeam: {team['display_name']} (ID: {team_id})")
                    
                    # Get channels for this team
                    print(f"Getting channels for team {team['display_name']}...")
                    channels = self.driver.channels.get_channels_for_user('me', team_id)
                    print(f"Found {len(channels)} channels in team {team['display_name']}")
                    
                    for channel in channels:
                        print(f"\nProcessing channel: {channel.get('display_name', channel.get('name', 'Unknown'))}")
                        print(f"Channel type: {channel.get('type', 'Unknown')}")
                        print(f"Channel ID: {channel['id']}")
                        
                        try:
                            self._update_channel_info(channel['id'])
                            print(f"Successfully added channel: {channel.get('display_name', channel.get('name', 'Unknown'))}")
                        except Exception as e:
                            print(f"Error adding channel: {str(e)}")
                            import traceback
                            print(f"Channel error traceback: {traceback.format_exc()}")
                            
                except Exception as e:
                    print(f"Error processing team {team_id}: {str(e)}")
                    import traceback
                    print(f"Team error traceback: {traceback.format_exc()}")

        except Exception as e:
            print(f"Error in initialization: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")

        print("\n=== Channel Initialization Summary ===")
        print(f"Bot is member of {len(self.channels)} channels:")
        for channel_id, info in self.channels.items():
            print(f"- Channel: {info['name']} (ID: {channel_id})")
            print(f"  Members: {len(info['members'])} users")
            print(f"  Member list: {info['members']}")
        print("=" * 50)
        
        print("\n=== Setting up Daily Reports ===")
        current_time = datetime.now(TIMEZONE)
        print(f"Current time: {current_time}")
        print(f"Configured report time: {REPORT_TIME}")
        print(f"Timezone: {TIMEZONE}")
        
        # Start the scheduler thread
        scheduler_thread = Thread(target=self._run_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        print("Scheduler thread started")

        # Keep your existing WebSocket initialization
        self.driver.init_websocket(self._handle_websocket_event)

    def _run_scheduler(self):
        print("\nScheduler thread starting...")
        last_run_date = None
        
        while True:
            try:
                current_time = datetime.now(TIMEZONE)
                current_hour = current_time.strftime('%H')
                current_minute = current_time.strftime('%M')
                current_date = current_time.strftime('%Y-%m-%d')
                
                print(f"\n=== Scheduler Check at {current_time.strftime('%Y-%m-%d %H:%M:%S')} ===")
                print(f"Current time: {current_hour}:{current_minute}")
                print(f"Target time: {REPORT_TIME}")
                
                # Check if it's time to run and we haven't run today
                target_hour, target_minute = REPORT_TIME.split(':')
                if (current_hour == target_hour and 
                    current_minute == target_minute and 
                    current_date != last_run_date):
                    
                    print(f"\n!!! TRIGGERING DAILY REPORT at {current_time} !!!")
                    self.send_daily_report()
                    last_run_date = current_date
                    print(f"Updated last run date to: {last_run_date}")
                
                time.sleep(60)
                
            except Exception as e:
                print(f"Error in scheduler loop: {str(e)}")
                print(f"Full error: {traceback.format_exc()}")
                time.sleep(60)

    def _check_reminders(self):
        current_time = datetime.now(TIMEZONE)
        for channel_id, channel_info in self.channels.items():
            if 'members' not in channel_info:
                continue

            reported_users = set(self.db.get_today_reports(channel_id))
            for member in channel_info['members']:
                if member in EXCLUDED_USERS or member == BOT_USERNAME:
                    continue

                if member not in reported_users:
                    reminder_key = f"{channel_id}_{member}"
                    if reminder_key not in self.pending_reminders:
                        report_time = datetime.strptime(REPORT_TIME, "%H:%M").time()
                        report_datetime = datetime.combine(current_time.date(), report_time)
                        report_datetime = report_datetime.replace(tzinfo=TIMEZONE)
                        if current_time > report_datetime + timedelta(hours=3):
                            self.pending_reminders[reminder_key] = current_time
                            self._send_reminder_dm(member)
                    else:
                        last_reminder = self.pending_reminders[reminder_key]
                        if current_time > last_reminder + timedelta(hours=REMINDER_INTERVAL):
                            self.pending_reminders[reminder_key] = current_time
                            self._send_reminder_dm(member)

    async def _handle_websocket_event(self, event):
        try:
            print(f"Received event type: {type(event)}")
            print(f"Received event content: {event}")
            
            # Parse the string event into a dictionary if it's a string
            if isinstance(event, str):
                try:
                    event = json.loads(event)
                    print(f"Parsed event into dict: {event}")
                except json.JSONDecodeError as e:
                    print(f"Failed to parse event as JSON: {e}")
                    return await asyncio.sleep(0)  # Return an awaitable

            # Debug the event structure
            print(f"Event keys: {event.keys() if isinstance(event, dict) else 'No keys (not a dict)'}")
            print(f"Event 'event' value: {event.get('event')}")
            print(f"Event 'data' value: {event.get('data')}")
            
            # Handle the initial hello event
            if event.get('event') == 'hello':
                print("Connected to websocket")
                return await asyncio.sleep(0)  # Return an awaitable
            
            # Only proceed if we have data and it's a post event
            if event.get('event') == 'posted':
                print("Handling posted event")
                data = event.get('data', {})
                print(f"Post data: {data}")
                
                if isinstance(data, dict) and 'post_id' in data:
                    post = self.driver.posts.get_post(data['post_id'])
                    print(f"Retrieved post: {post}")
                    
                    if post['user_id'] != self.bot_id:  # Ignore bot's own messages
                        if post.get('root_id'):  # This is a reply in a thread
                            self._handle_report_reply(post)
                        else:
                            self._handle_channel_message(post)
                else:
                    print(f"Invalid post data structure: {data}")
            
            return await asyncio.sleep(0)  # Return an awaitable

        except Exception as e:
            print(f"Error in websocket event handler: {e}")
            print(f"Error type: {type(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return await asyncio.sleep(0)  # Return an awaitable

    def _handle_report_reply(self, post):
        channel_id = post['channel_id']
        username = self.driver.users.get_user(post['user_id'])['username']
        
        if not self.db.has_reported_today(channel_id, username):
            channel = self.driver.channels.get_channel(channel_id)
            self.db.add_report(
                channel_id,
                channel['name'],
                username,
                post['message']
            )
            # Remove from pending reminders if exists
            reminder_key = f"{channel_id}_{username}"
            self.pending_reminders.pop(reminder_key, None)

    def _handle_channel_message(self, post):
        # Update channel info when bot receives a message
        channel_id = post['channel_id']
        if channel_id not in self.channels:
            self._update_channel_info(channel_id)

    def _update_channel_info(self, channel_id):
        channel = self.driver.channels.get_channel(channel_id)
        members = self.driver.channels.get_channel_members(channel_id)
        member_usernames = [
            self.driver.users.get_user(member['user_id'])['username']
            for member in members
        ]
        self.channels[channel_id] = {
            'name': channel['name'],
            'members': member_usernames
        }

    def send_daily_report(self):
        try:
            current_time = datetime.now(TIMEZONE)
            print(f"\n{'='*50}")
            print(f"=== EXECUTING DAILY REPORT at {current_time} ===")
            print(f"Current weekday: {current_time.strftime('%A')}")
            
            # Check if it's a reporting day
            if current_time.strftime("%A").lower() not in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']:
                print(f"Skipping report - not a reporting day ({current_time.strftime('%A')})")
                return
            
            print(f"\nProcessing {len(self.channels)} channels...")
            
            for channel_id, channel_info in self.channels.items():
                try:
                    channel_name = channel_info.get('name', '')
                    print(f"\nProcessing channel: {channel_name} ({channel_id})")
                    
                    # Skip DM channels - they will have names like user1__user2
                    if '__' in channel_name or channel_name == '':
                        print(f"Skipping DM channel: {channel_name}")
                        continue
                    
                    # Create user tags for all members except excluded users and the bot
                    user_tags = []
                    for member in channel_info.get('members', []):
                        if member not in EXCLUDED_USERS and member != BOT_USERNAME:
                            user_tags.append(f"@{member}")
                    
                    # Format the date
                    date_str = current_time.strftime("%A, %B %d, %Y")
                    
                    # Construct the message with date and user tags
                    message = (
                        f"## 🔔 **Daily Scrum Report for {date_str}**\n\n"
                        f"{' '.join(user_tags)}\n\n"
                        "Please reply to this thread with your daily report using the following format:\n\n"
                        "1. What did you accomplish yesterday?\n"
                        "2. What are you working on today?\n"
                        "3. Any blockers or challenges?\n\n"
                        "**I'm a bot but I'm keeping records of your reports, your daily report misses, and send it daily to the project manager**"
                    )
                    
                    print(f"Attempting to send message to channel {channel_name}...")
                    try:
                        post = self.driver.posts.create_post({
                            'channel_id': channel_id,
                            'message': message
                        })
                        print(f"✅ Message sent successfully to {channel_name}! Post ID: {post['id']}")
                    except Exception as e:
                        print(f"❌ Error sending message: {str(e)}")
                        print(f"Full error: {traceback.format_exc()}")
                    
                    # Initialize empty pending reminders for this channel
                    self.pending_reminders[channel_id] = []
                    
                except Exception as e:
                    print(f"Error processing channel {channel_info.get('name', 'Unknown')}: {str(e)}")
                    print(f"Full error: {traceback.format_exc()}")
            
            print("\n=== Daily report execution completed ===")
            print("=" * 50)
        except Exception as e:
            print(f"Critical error in send_daily_report: {str(e)}")
            print(f"Full error: {traceback.format_exc()}")

    def _send_reminder_dm(self, username):
        try:
            # Create or get DM channel
            user = self.driver.users.get_user_by_username(username)
            dm_channel = self.driver.channels.create_direct_message_channel([self.bot_id, user['id']])
            
            # Send reminder message
            self.driver.posts.create_post({
                'channel_id': dm_channel['id'],
                'message': REMINDER_MESSAGE
            })
            print(f"Reminder sent to {username}")
        except Exception as e:
            print(f"Error sending reminder to {username}: {str(e)}")

if __name__ == "__main__":
    bot = ScrumBot()
    print("Bot started")
    bot.start() 
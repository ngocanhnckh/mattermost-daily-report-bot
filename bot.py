import time
import schedule
from datetime import datetime, timedelta
from threading import Thread
from mattermostdriver import Driver
from database import Database
from ai_validator import AIValidator
import traceback
from config import (
    MATTERMOST_URL, BOT_TOKEN, BOT_USERNAME,
    REPORT_TIME, REMINDER_INTERVAL, EXCLUDED_USERS,
    DAILY_REPORT_MESSAGE, REMINDER_MESSAGE, TIMEZONE,
    AI_VALIDATION_ENABLED, OPENROUTER_API_KEY, SITE_URL, SITE_NAME,
    TEAM_NAME
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
        self.pending_reminders = {}  # Format: {channel_id: {username: last_reminder_time}}
        self.daily_report_posts = {}  # Store daily report post IDs for each channel
        
        # Initialize AI validator
        self.ai_validator = AIValidator(
            api_key=OPENROUTER_API_KEY,
            site_url=SITE_URL,
            site_name=SITE_NAME,
            enabled=AI_VALIDATION_ENABLED
        )

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
                            print(f"Channel error traceback: {traceback.format_exc()}")
                            
                except Exception as e:
                    print(f"Error processing team {team_id}: {str(e)}")
                    print(f"Team error traceback: {traceback.format_exc()}")

        except Exception as e:
            print(f"Error in initialization: {str(e)}")
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
        print(f"Setting report time to: {REPORT_TIME}")
        print(f"Timezone: {TIMEZONE}")
        print(f"Reminder interval: {REMINDER_INTERVAL} hours")
        
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
                
                # Check reminders every minute
                self._check_reminders()
                print("Checked reminders")
                
                time.sleep(60)  # Check every minute
                
            except Exception as e:
                print(f"Error in scheduler loop: {str(e)}")
                print(f"Full error: {traceback.format_exc()}")
                time.sleep(60)

    def _check_reminders(self):
        current_time = datetime.now(TIMEZONE)
        print("\n=== Checking Reminders ===")
        print(f"Current time: {current_time}")
        
        # Track who we've reminded this round to avoid duplicates across channels
        reminded_this_round = set()
        
        # Only check channels that have an active daily report
        for channel_id, report_info in self.daily_report_posts.items():
            channel_info = self.channels.get(channel_id, {})
            print(f"\nChecking channel: {channel_info.get('name', 'Unknown')} ({channel_id})")
            
            # Initialize pending reminders for this channel if not exists
            if channel_id not in self.pending_reminders:
                self.pending_reminders[channel_id] = {}
            
            # Get users who have reported in this specific channel today
            reported_users_in_channel = set(self.db.get_today_reports(channel_id))
            print(f"Users who have reported in this channel today: {reported_users_in_channel}")
            
            if 'members' not in channel_info:
                print("No members found in channel info")
                continue
            
            for member in channel_info['members']:
                # Skip if we've already reminded this user in this round or if they're excluded/bot
                if (member in reminded_this_round or 
                    member in EXCLUDED_USERS or 
                    member == BOT_USERNAME):
                    print(f"Skipping {member} - already reminded this round or excluded")
                    continue
                
                # If user has reported in this channel, remove them from this channel's pending reminders
                if member in reported_users_in_channel:
                    print(f"Skipping {member} - has reported in this channel today")
                    if member in self.pending_reminders[channel_id]:
                        print(f"Removing {member} from pending reminders for channel {channel_id}")
                        self.pending_reminders[channel_id].pop(member, None)
                    continue

                print(f"\nChecking member: {member} for channel: {channel_id}")
                
                report_time = datetime.strptime(REPORT_TIME, "%H:%M").time()
                report_datetime = datetime.combine(current_time.date(), report_time)
                report_datetime = report_datetime.replace(tzinfo=TIMEZONE)
                
                # Use REMINDER_INTERVAL for first reminder too
                if current_time >= report_datetime + timedelta(hours=REMINDER_INTERVAL):
                    print(f"Time to send/update reminder for {member} in channel {channel_id}")
                    if member not in self.pending_reminders[channel_id]:
                        print(f"First reminder for {member} in channel {channel_id}")
                        self.pending_reminders[channel_id][member] = current_time
                        self._send_reminder_dm(member)
                        reminded_this_round.add(member)
                    else:
                        last_reminder = self.pending_reminders[channel_id][member]
                        # Use REMINDER_INTERVAL and >= for subsequent reminders
                        if current_time >= last_reminder + timedelta(hours=REMINDER_INTERVAL):
                            print(f"Follow-up reminder for {member} in channel {channel_id}")
                            self.pending_reminders[channel_id][member] = current_time
                            self._send_reminder_dm(member)
                            reminded_this_round.add(member)
                        else:
                            print(f"Too soon for next reminder. Last reminder was at {last_reminder}")
                else:
                    print(f"Too soon to send reminder. Need to wait until {report_datetime + timedelta(hours=REMINDER_INTERVAL)}")

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
                
                # Parse the post data if it's a string
                if isinstance(data.get('post'), str):
                    try:
                        post_data = json.loads(data['post'])
                        print(f"Parsed post data: {post_data}")
                        
                        if post_data['user_id'] != self.bot_id:  # Ignore bot's own messages
                            if post_data.get('root_id'):  # This is a reply in a thread
                                self._handle_report_reply(post_data)
                            else:
                                self._handle_channel_message(post_data)
                    except json.JSONDecodeError as e:
                        print(f"Failed to parse post data: {e}")
                
            return await asyncio.sleep(0)  # Return an awaitable

        except Exception as e:
            print(f"Error in websocket event handler: {e}")
            print(f"Error type: {type(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            return await asyncio.sleep(0)  # Return an awaitable

    def _handle_report_reply(self, post):
        try:
            channel_id = post['channel_id']
            root_id = post.get('root_id', '')
            
            # Check if this reply is in a daily report thread
            if channel_id not in self.daily_report_posts or \
               self.daily_report_posts[channel_id]['post_id'] != root_id:
                print(f"Ignoring reply - not in a daily report thread")
                return
            
            username = self.driver.users.get_user(post['user_id'])['username']
            message = post['message']
            
            print(f"\n=== Handling Report Reply ===")
            print(f"Channel ID: {channel_id}")
            print(f"Username: {username}")
            print(f"Message: {message}")
            print(f"AI Validation Enabled: {self.ai_validator.enabled}")
            
            # Validate report with AI if enabled
            print("\nStarting AI validation...")
            validation_result = self.ai_validator.validate_report(message)
            print(f"Validation result: {validation_result}")
            
            if validation_result["valid"]:
                print("Report is valid, checking if user already reported today...")
                if not self.db.has_reported_today(channel_id, username):
                    print("User has not reported today, adding report to database...")
                    channel = self.driver.channels.get_channel(channel_id)
                    self.db.add_report(
                        channel_id,
                        channel['name'],
                        username,
                        message
                    )
                    print(f"Added report for {username}")
                    
                    # Remove from pending reminders for this specific channel if exists
                    if channel_id in self.pending_reminders and username in self.pending_reminders[channel_id]:
                        print(f"Removing {username} from pending reminders for channel {channel_id}")
                        self.pending_reminders[channel_id].pop(username, None)
                else:
                    print(f"User {username} has already reported today")
            else:
                print("Report is not valid")
            
            # Send feedback to the user
            if validation_result["message"]:
                print(f"Sending feedback to user: {validation_result['message']}")
                # Get the root_id from the post data
                root_id = post.get('root_id', '')
                if not root_id:
                    root_id = post.get('id', '')  # If no root_id, use the post's own id
                
                print(f"Using root_id: {root_id}")
                post_data = {
                    'channel_id': channel_id,
                    'message': f"@{username} {validation_result['message']}"
                }
                
                # Only add root_id if it exists
                if root_id:
                    post_data['root_id'] = root_id
                    
                self.driver.posts.create_post(post_data)
                print("Feedback sent successfully")
                
        except Exception as e:
            print(f"Error handling report reply: {e}")
            print(f"Full error: {traceback.format_exc()}")
            print(f"Post data: {post}")

    def _handle_channel_message(self, post):
        # Update channel info when bot receives a message
        channel_id = post['channel_id']
        if channel_id not in self.channels:
            self._update_channel_info(channel_id)

    def _update_channel_info(self, channel_id):
        channel = self.driver.channels.get_channel(channel_id)
        
        # Skip Town Square channel
        if channel['name'] == 'town-square':
            print(f"Skipping Town Square channel")
            return
            
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
            
            # Clear previous daily report posts and pending reminders
            self.daily_report_posts.clear()
            self.pending_reminders.clear()
            
            for channel_id, channel_info in self.channels.items():
                try:
                    channel_name = channel_info.get('name', '')
                    print(f"\nProcessing channel: {channel_name} ({channel_id})")
                    
                    # Skip DM channels and Town Square
                    if '__' in channel_name or channel_name == '' or channel_name == 'town-square':
                        print(f"Skipping channel: {channel_name}")
                        continue
                    
                    # Create user tags for all members except excluded users and the bot
                    user_tags = []
                    requested_users = []  # Track users who are being requested to report
                    for member in channel_info.get('members', []):
                        if member not in EXCLUDED_USERS and member != BOT_USERNAME:
                            user_tags.append(f"@{member}")
                            requested_users.append(member)
                    
                    # Format the date
                    date_str = current_time.strftime("%A, %B %d, %Y")
                    
                    # Construct the message with date, user tags, and the configured message
                    message = (
                        f"## 🔔 **Daily Scrum Report for {date_str}**\n\n"
                        f"{' '.join(user_tags)}\n\n"
                        f"{DAILY_REPORT_MESSAGE}"
                    )
                    
                    print(f"Attempting to send message to channel {channel_name}...")
                    try:
                        post = self.driver.posts.create_post({
                            'channel_id': channel_id,
                            'message': message
                        })
                        print(f"✅ Message sent successfully to {channel_name}! Post ID: {post['id']}")
                        
                        # Store the post ID for this channel
                        self.daily_report_posts[channel_id] = {
                            'post_id': post['id'],
                            'channel_name': channel_name
                        }
                        
                        # Initialize empty pending reminders for this channel
                        self.pending_reminders[channel_id] = {}
                        
                        # Record the bot's request in the database
                        self.db.add_bot_request(channel_id, channel_name, requested_users)
                        print(f"Recorded report request for {len(requested_users)} users in {channel_name}")
                        
                    except Exception as e:
                        print(f"❌ Error sending message: {str(e)}")
                        print(f"Full error: {traceback.format_exc()}")
                    
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
            
            # Format the date
            current_time = datetime.now(TIMEZONE)
            date_str = current_time.strftime("%A, %B %d, %Y")
            
            # Find the channels where this user needs to report
            user_pending_channels = []
            for channel_id, report_info in self.daily_report_posts.items():
                channel_info = self.channels.get(channel_id, {})
                if username in channel_info.get('members', []):
                    # Check if user has reported in this channel
                    reported_users = set(self.db.get_today_reports(channel_id))
                    if username not in reported_users:
                        channel_name = report_info['channel_name']
                        post_id = report_info['post_id']
                        # Include team name in the thread link
                        thread_link = f"{SITE_URL}/{TEAM_NAME}/pl/{post_id}"
                        user_pending_channels.append(f"[{channel_name}]({thread_link})")
            
            # Only send reminder if there are pending channels
            if user_pending_channels:
                # Add date and thread links to the reminder message
                message = (
                    f"{REMINDER_MESSAGE}"
                    f"⏰ **Daily Report Reminder for {date_str}**\n\n"
                    f"You still need to submit your daily report in the following channels:\n"
                )
                
                for channel_link in user_pending_channels:
                    message += f"• {channel_link}\n"
                
                # Send reminder message
                self.driver.posts.create_post({
                    'channel_id': dm_channel['id'],
                    'message': message
                })
                print(f"Reminder sent to {username} for {len(user_pending_channels)} pending channels")
            else:
                print(f"No pending channels to remind {username} about")
                
        except Exception as e:
            print(f"Error sending reminder to {username}: {str(e)}")

if __name__ == "__main__":
    bot = ScrumBot()
    print("Bot started")
    bot.start() 
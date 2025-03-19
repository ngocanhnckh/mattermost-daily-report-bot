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
    TEAM_NAME, REPORT_DEADLINE_TIME, USER_MAPPINGS, CHANNEL_MAPPINGS,
    REMIND_TASK_MESSAGE, JIRA_URL
)
import ssl
from urllib.parse import urlparse
import json
import asyncio
from jira_service import JiraService
from message_analyzer import MessageAnalyzer
from typing import List, Dict

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

        # Initialize Jira service with the same AI parameters
        self.jira_service = JiraService(
            api_key=OPENROUTER_API_KEY,
            site_url=SITE_URL,
            site_name=SITE_NAME,
            enabled=AI_VALIDATION_ENABLED
        )

        # Initialize message analyzer
        self.message_analyzer = MessageAnalyzer(
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
        
        # Check if it's deadline time
        deadline_time = datetime.strptime(REPORT_DEADLINE_TIME, "%H:%M").time()
        is_deadline = current_time.time() >= deadline_time
        
        for channel_id, report_info in self.daily_report_posts.items():
            channel_info = self.channels.get(channel_id, {})
            channel_name = channel_info.get('name', 'Unknown')
            
            # Get Jira project code for this channel
            jira_project = CHANNEL_MAPPINGS.get(channel_name, {}).get('jira_project')
            print(f"\nProcessing channel: {channel_name} (Jira: {jira_project})")
            
            for member in channel_info.get('members', []):
                if member in EXCLUDED_USERS or member == BOT_USERNAME:
                    continue
                    
                # Get user's Jira mapping
                user_info = USER_MAPPINGS.get(member)
                if not user_info:
                    print(f"No Jira mapping found for user {member}")
                    continue
                    
                print(f"\nChecking tasks for {member} ({user_info['jira_username']})")
                
                # Get active tasks
                tasks = self.jira_service.get_user_active_tasks(
                    user_info['jira_username'],
                    jira_project
                )
                
                if is_deadline and not self.db.has_reported_today(channel_id, member):
                    print(f"Deadline reached for {member}, checking activities...")
                    
                    # Get both messages and Jira updates
                    messages = self._get_user_recent_messages(channel_id, member)
                    recent_updates = self.jira_service.get_user_recent_updates(
                        user_info['jira_username'],
                        jira_project
                    )
                    
                    # Generate report if we have either messages or Jira updates
                    if messages or recent_updates:
                        ai_report = self.message_analyzer.generate_report(
                            member,
                            messages,
                            tasks,
                            recent_updates
                        )
                        if ai_report:
                            self._send_ai_generated_report(
                                channel_id,
                                member,
                                ai_report,
                                self.daily_report_posts[channel_id]['post_id']
                            )
                    else:
                        print(f"No recent activity found for {member}, skipping AI report")
                
                elif tasks:  # Regular reminder with task context
                    # Identify urgent tasks (due within 1 day)
                    urgent_tasks = [
                        task for task in tasks
                        if task['end_date'] and 
                        task['end_date'].date() <= (current_time + timedelta(days=1)).date()
                    ]
                    
                    self._send_task_reminder(
                        member,
                        tasks,
                        urgent_tasks,
                        channel_id
                    )

    def _get_user_recent_messages(self, channel_id: str, username: str) -> List[str]:
        """Get user's messages from the last 2 days."""
        try:
            # Calculate start time (beginning of yesterday)
            start_time = int((datetime.now(TIMEZONE) - timedelta(days=1))
                           .replace(hour=0, minute=0, second=0)
                           .timestamp() * 1000)
            
            # Get user ID
            user = self.driver.users.get_user_by_username(username)
            
            # Get posts
            posts = self.driver.posts.get_posts_for_channel(channel_id)
            
            # Filter posts by user and time
            user_messages = []
            for post in posts['posts'].values():
                post_time = datetime.fromtimestamp(post['create_at']/1000, TIMEZONE)
                if (post['user_id'] == user['id'] and 
                    post_time >= datetime.fromtimestamp(start_time/1000, TIMEZONE)):
                    user_messages.append(post['message'])
            
            print(f"Found {len(user_messages)} recent messages for {username}")
            return user_messages
            
        except Exception as e:
            print(f"Error getting recent messages: {e}")
            print(f"Full error: {traceback.format_exc()}")
            return []

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
                
                if isinstance(data.get('post'), str):
                    try:
                        post_data = json.loads(data['post'])
                        print(f"Parsed post data: {post_data}")
                        
                        if post_data['user_id'] != self.bot_id:  # Ignore bot's own messages
                            # Check if bot is mentioned
                            if f'@{BOT_USERNAME}' in post_data['message']:
                                self._handle_bot_mention(post_data)
                            elif post_data.get('root_id'):  # This is a reply in a thread
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
            
            # Get channel info and project code
            channel_info = self.channels.get(channel_id, {})
            channel_name = channel_info.get('name', '')
            channel_mapping = CHANNEL_MAPPINGS.get(channel_name, {})
            project_code = channel_mapping.get('jira_project')
            
            if not project_code:
                print(f"No Jira project mapping found for channel {channel_name}")
                return
            
            # Get channel members with their details
            channel_members = {
                member: USER_MAPPINGS.get(member, {})
                for member in channel_info.get('members', [])
                if member not in EXCLUDED_USERS and member != BOT_USERNAME
            }
            
            # Validate report with AI
            print("\nStarting AI validation...")
            validation_result = self.ai_validator.validate_report(message)
            print(f"Validation result: {validation_result}")
            
            # Handle blocker if detected
            if validation_result.get('has_blocker'):
                print("\nBlocker detected, creating Jira task...")
                blocker_task = self.jira_service.create_blocker_task(
                    project_code=project_code,
                    blocker_details=validation_result['blocker_details'],
                    reporter_username=username,
                    channel_members=channel_members
                )
                
                if blocker_task:
                    # Create notification message
                    notification = (
                        f"🚨 **New Blocker Task Created**\n\n"
                        f"@{blocker_task['assignee']} A new blocker has been assigned to you:\n"
                        f"[{blocker_task['key']}]({blocker_task['url']}): {blocker_task['summary']}\n\n"
                        f"This blocker was reported by @{username} in their daily report.\n\n"
                        f"*Assignment Reasoning:* {blocker_task.get('reasoning', 'No reasoning provided')}"
                    )
                    
                    # Send notification to channel (outside the thread)
                    self.driver.posts.create_post({
                        'channel_id': channel_id,
                        'message': notification
                    })
            
            # Continue with existing report validation logic...
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
            
            if current_time.strftime("%A").lower() not in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']:
                print(f"Skipping report - not a reporting day ({current_time.strftime('%A')})")
                return
            
            print(f"\nProcessing {len(self.channels)} channels...")
            
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
                    
                    # Get Jira project code for this channel
                    channel_mapping = CHANNEL_MAPPINGS.get(channel_name)
                    if not channel_mapping:
                        print(f"No Jira mapping found for channel {channel_name}, skipping")
                        continue
                        
                    jira_project = channel_mapping.get('jira_project')
                    if not jira_project:
                        print(f"No Jira project code found for channel {channel_name}, skipping")
                        continue
                    
                    print(f"Found Jira project mapping: {channel_name} -> {jira_project}")
                    
                    # Step 1: Validate and update sprint tasks
                    print("\nValidating sprint tasks before daily report...")
                    member_mappings = {
                        member: USER_MAPPINGS[member]['jira_username']
                        for member in channel_info.get('members', [])
                        if member not in EXCLUDED_USERS 
                        and member != BOT_USERNAME 
                        and member in USER_MAPPINGS
                    }
                    
                    update_results = self.jira_service.validate_and_update_sprint_tasks(
                        jira_project,
                        member_mappings
                    )
                    
                    # Send update report to channel if any tasks were updated
                    if update_results.get('updated', 0) > 0:
                        update_message = (
                            f"🔄 **Sprint Task Updates**\n\n"
                            f"Updated {update_results['updated']} tasks with missing information:\n\n"
                        )
                        for task in update_results['tasks']:
                            # Add task update info with summary
                            update_message += (
                                f"### [{task['key']}]({JIRA_URL}/browse/{task['key']}): {task['summary']}\n"
                                f"- Updated fields: {', '.join(task['updated_fields'])}\n"
                            )
                            
                            # Add AI's reasoning if available
                            if task.get('reasoning'):
                                update_message += "\n**AI's Decision Making:**\n"
                                for aspect, explanation in task['reasoning'].items():
                                    aspect_title = aspect.replace('_', ' ').title()
                                    update_message += f"- {aspect_title}: {explanation}\n"
                            update_message += "\n"  # Add extra line break between tasks
                        
                        self.driver.posts.create_post({
                            'channel_id': channel_id,
                            'message': update_message
                        })
                    
                    # Track users with tasks
                    users_with_tasks = []
                    task_messages = []
                    
                    # Check tasks for each member
                    for member in channel_info.get('members', []):
                        if member in EXCLUDED_USERS or member == BOT_USERNAME:
                            print(f"Skipping excluded user: {member}")
                            continue
                        
                        # Get user's Jira mapping
                        user_info = USER_MAPPINGS.get(member)
                        if not user_info:
                            print(f"No Jira mapping found for user {member}, skipping")
                            continue
                            
                        jira_username = user_info.get('jira_username')
                        if not jira_username:
                            print(f"No Jira username found for user {member}, skipping")
                            continue
                        
                        print(f"\nChecking tasks for {member} ({jira_username})")
                        
                        # Get active tasks
                        tasks = self.jira_service.get_user_active_tasks(jira_username, jira_project)
                        
                        if tasks:
                            # Sort tasks by end date and status
                            todo_tasks = [t for t in tasks if t['status'] == 'To Do']
                            in_progress_tasks = [t for t in tasks if t['status'] == 'In Progress']
                            
                            for task_list in [todo_tasks, in_progress_tasks]:
                                task_list.sort(key=lambda x: (
                                    x['end_date'] if x['end_date'] else datetime.max,
                                    x['key']
                                ))
                            
                            users_with_tasks.append(member)
                            user_tasks = []
                            
                            # Add in-progress tasks first
                            for task in in_progress_tasks[:2]:
                                urgent = ""
                                if task['end_date'] and task['end_date'].date() <= (current_time + timedelta(days=1)).date():
                                    urgent = "🚨 **URGENT**"
                                user_tasks.append(
                                    f"- [{task['key']}]({task['url']}): {task['summary']} "
                                    f"({task['status']}) {urgent}"
                                )
                            
                            # Add to-do tasks
                            remaining_slots = 2 - len(user_tasks)
                            for task in todo_tasks[:remaining_slots]:
                                urgent = ""
                                if task['end_date'] and task['end_date'].date() <= (current_time + timedelta(days=1)).date():
                                    urgent = "🚨 **URGENT**"
                                user_tasks.append(
                                    f"- [{task['key']}]({task['url']}) {task['summary']} "
                                    f"({task['status']}) {urgent}"
                                )
                            
                            if user_tasks:
                                task_messages.append(f"--------------------------------\n @{member}, {REMIND_TASK_MESSAGE}\n" + "\n".join(user_tasks))
                    
                    if users_with_tasks:
                        # Construct the message
                        date_str = current_time.strftime("%A, %B %d, %Y")
                        message = (
                            f"## 🔔 **Daily Scrum Report for {date_str}**\n\n"
                            f"{' '.join(f'@{user}' for user in users_with_tasks)}\n\n"
                        )
                        message += DAILY_REPORT_MESSAGE
                        
                        if task_messages:
                            message += "\n---------------------------------------------------------\n"
                            message += "\n### Task Updates:\n" + "\n\n".join(task_messages) + "\n\n"
                            
                        
                        
                        print(f"Sending daily report to channel {channel_name}")
                        post = self.driver.posts.create_post({
                            'channel_id': channel_id,
                            'message': message
                        })
                        
                        # Store the post ID
                        self.daily_report_posts[channel_id] = {
                            'post_id': post['id'],
                            'channel_name': channel_name
                        }
                        
                        # Initialize pending reminders
                        self.pending_reminders[channel_id] = {}
                        
                        # Record the request
                        self.db.add_bot_request(channel_id, channel_name, users_with_tasks)
                        print(f"Recorded report request for {len(users_with_tasks)} users in {channel_name}")
                    else:
                        print(f"No users with active tasks in {channel_name}, skipping")
                    
                except Exception as e:
                    print(f"Error processing channel {channel_info.get('name', 'Unknown')}: {str(e)}")
                    print(f"Full error: {traceback.format_exc()}")
            
            print("\n=== Daily report execution completed ===")
            print("=" * 50)
            
        except Exception as e:
            print(f"Critical error in send_daily_report: {str(e)}")
            print(f"Full error: {traceback.format_exc()}")

    def _format_daily_report_message(self, channel_id: str, channel_name: str) -> tuple[str, list[str]]:
        """Format the daily report message with user tasks.
        Returns tuple of (message, tagged_users)"""
        try:
            date_str = datetime.now(TIMEZONE).strftime("%A, %B %d, %Y")
            tagged_users = []
            user_task_mentions = []

            # Get Jira project code for this channel
            jira_project = CHANNEL_MAPPINGS.get(channel_name, {}).get('jira_project')
            print(f"\nGetting tasks for channel {channel_name} (Jira: {jira_project})")

            if jira_project and self.jira_service.enabled:
                for member in self.channels[channel_id].get('members', []):
                    if member in EXCLUDED_USERS or member == BOT_USERNAME:
                        continue

                    # Get user's Jira mapping
                    user_info = USER_MAPPINGS.get(member, {})
                    jira_username = user_info.get('jira_username', member)
                    
                    # Get active tasks
                    tasks = self.jira_service.get_user_active_tasks(jira_username, jira_project)
                    
                    # Sort tasks by end date and status
                    todo_tasks = [t for t in tasks if t['status'] == 'To Do']
                    in_progress_tasks = [t for t in tasks if t['status'] == 'In Progress']
                    
                    # Sort by end date if available
                    for task_list in [todo_tasks, in_progress_tasks]:
                        task_list.sort(key=lambda x: (
                            x['end_date'] if x['end_date'] else datetime.max,
                            x['key']
                        ))

                    if tasks:  # Only tag users with active tasks
                        tagged_users.append(member)
                        user_mention = f"@{member}"
                        task_mentions = []
                        
                        # Add in-progress tasks first
                        for task in in_progress_tasks[:2]:  # Max 2 tasks
                            urgent = ""
                            if task['end_date']:
                                if task['end_date'].date() <= (datetime.now(TIMEZONE) + timedelta(days=1)).date():
                                    urgent = "🚨 **URGENT**"
                            task_mentions.append(
                                f"- [{task['key']}]({task['url']}): {task['summary']} "
                                f"({task['status']}) {urgent}"
                            )
                        
                        # Add to-do tasks
                        remaining_slots = 2 - len(task_mentions)
                        for task in todo_tasks[:remaining_slots]:
                            urgent = ""
                            if task['end_date']:
                                if task['end_date'].date() <= (datetime.now(TIMEZONE) + timedelta(days=1)).date():
                                    urgent = "🚨 **URGENT**"
                            task_mentions.append(
                                f"- [{task['key']}]({task['url']}): {task['summary']} "
                                f"({task['status']}) {urgent}"
                            )
                        
                        if task_mentions:
                            user_task_mentions.append(f"{user_mention}, {REMIND_TASK_MESSAGE}:\n" + "\n".join(task_mentions))

            # Construct the final message
            message = (
                f"## 🔔 **Daily Scrum Report for {date_str}**\n\n"
                f"{' '.join(f'@{user}' for user in tagged_users)}\n\n"
            )
            
            if user_task_mentions:
                message += "\n### Active Tasks:\n" + "\n\n".join(user_task_mentions) + "\n\n"
            
            message += DAILY_REPORT_MESSAGE
            
            return message, tagged_users

        except Exception as e:
            print(f"Error formatting daily report message: {e}")
            print(f"Full error: {traceback.format_exc()}")
            # Return default message as fallback
            return DAILY_REPORT_MESSAGE, []

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

    def _send_ai_generated_report(self, channel_id: str, username: str, ai_report: str, root_id: str):
        """Send an AI-generated report as a reply in the daily report thread."""
        try:
            print(f"\n=== Sending AI-generated report for {username} ===")
            
            # Get channel info
            channel = self.driver.channels.get_channel(channel_id)
            print(f"Channel: {channel.get('name', 'Unknown')}")
            
            # Format the message
            message = (
                f"@{username} Since you haven't submitted a report yet, "
                f"here's an AI-generated report based on your recent activities:\n\n"
                f"{ai_report}\n\n"
                f"_Note: This is an automated report. Please submit your own report if this is inaccurate._"
            )
            
            # Send as a reply in the daily report thread
            print("Sending AI report to Mattermost...")
            post = self.driver.posts.create_post({
                'channel_id': channel_id,
                'message': message,
                'root_id': root_id  # Use the provided root_id
            })
            
            if post:
                print("Storing AI report in database...")
                self.db.add_report(
                    channel_id=channel_id,
                    channel_name=channel['name'],
                    username=username,
                    message=ai_report,
                    is_ai_generated=True
                )
                print("AI report sent and stored successfully")
            else:
                print("Failed to create post in Mattermost")
            
        except Exception as e:
            print(f"Error sending AI-generated report: {e}")
            print(f"Full error: {traceback.format_exc()}")

    def _send_task_reminder(self, username: str, tasks: List[Dict], urgent_tasks: List[Dict], channel_id: str):
        """Send a reminder with task information to a user.
        
        Args:
            username (str): The username to remind
            tasks (List[Dict]): List of all active tasks
            urgent_tasks (List[Dict]): List of urgent tasks (due within 1 day)
            channel_id (str): The channel ID
        """
        try:
            print(f"\n=== Sending task reminder to {username} ===")
            
            # Create or get DM channel
            user = self.driver.users.get_user_by_username(username)
            dm_channel = self.driver.channels.create_direct_message_channel([self.bot_id, user['id']])
            
            # Format the task information
            task_info = []
            
            # Add urgent tasks first with warning emoji
            for task in urgent_tasks:
                due_date = task['end_date'].strftime('%Y-%m-%d') if task['end_date'] else 'No due date'
                task_info.append(
                    f"🚨 **URGENT** [{task['key']}]({task['url']}): {task['summary']}\n"
                    f"   Status: {task['status']}, Due: {due_date}"
                )
            
            # Add other tasks
            other_tasks = [t for t in tasks if t not in urgent_tasks]
            for task in other_tasks:
                due_date = task['end_date'].strftime('%Y-%m-%d') if task['end_date'] else 'No due date'
                task_info.append(
                    f"• [{task['key']}]({task['url']}): {task['summary']}\n"
                    f"   Status: {task['status']}, Due: {due_date}"
                )
            
            # Format the message
            message = (
                f"{REMINDER_MESSAGE}\n\n"
                f"Your active tasks:\n"
                f"{chr(10).join(task_info)}\n\n"
                f"Please reply in the daily report thread: {SITE_URL}/{TEAM_NAME}/pl/{self.daily_report_posts[channel_id]['post_id']}"
            )
            
            # Send the reminder
            self.driver.posts.create_post({
                'channel_id': dm_channel['id'],
                'message': message
            })
            
            print(f"Reminder sent to {username} with {len(tasks)} tasks ({len(urgent_tasks)} urgent)")
            
        except Exception as e:
            print(f"Error sending task reminder to {username}: {e}")
            print(f"Full error: {traceback.format_exc()}")

    def _handle_bot_mention(self, post_data):
        try:
            # Get the root_id - if this is a thread reply, use the parent thread's id
            root_id = post_data.get('root_id') or post_data.get('id')
            
            channel_id = post_data['channel_id']
            user_id = post_data['user_id']
            message = post_data['message'].replace(f'@{BOT_USERNAME}', '').strip()  # Remove bot mention
            
            # Get channel info
            channel_info = self.channels.get(channel_id, {})
            channel_name = channel_info.get('name', '')
            
            # Get Jira project code
            channel_mapping = CHANNEL_MAPPINGS.get(channel_name, {})
            project_code = channel_mapping.get('jira_project')
            
            if not project_code:
                self.driver.posts.create_post({
                    'channel_id': channel_id,
                    'message': "Sorry, this channel is not configured with a Jira project.",
                    'root_id': root_id
                })
                return
            
            # Get user info
            username = self.driver.users.get_user(user_id)['username']
            
            # Get prior messages
            posts = self.driver.posts.get_posts_for_channel(channel_id)
            prior_messages = []
            
            # Check if this is a thread reply
            is_thread_reply = bool(post_data.get('root_id'))
            
            for post in sorted(posts['posts'].values(), key=lambda x: x['create_at'], reverse=True):
                if post['id'] != post_data['id']:  # Skip the current message
                    # For thread replies, only include messages from the same thread
                    if is_thread_reply:
                        if post.get('root_id') == post_data['root_id'] or post['id'] == post_data['root_id']:
                            user = self.driver.users.get_user(post['user_id'])['username']
                            prior_messages.append(f"@{user}: {post['message']}")
                    else:
                        # For root messages, include all messages
                        user = self.driver.users.get_user(post['user_id'])['username']
                        prior_messages.append(f"@{user}: {post['message']}")
                        
                # Limit to 10 messages
                if len(prior_messages) >= 15:
                    break
            
            # Get recently updated tasks for this project
            active_tasks = self.jira_service.get_recent_project_tasks(project_code)
            
            # Get channel members with their details
            channel_members = {
                member: USER_MAPPINGS.get(member, {})
                for member in channel_info.get('members', [])
                if member not in EXCLUDED_USERS and member != BOT_USERNAME
            }
            
            # Analyze the question
            analysis = self.ai_validator.analyze_question(
                message,
                prior_messages,
                active_tasks,
                channel_members
            )
            
            if analysis['needs_action']:
                created_tasks = []
                updated_tasks = []
                
                if analysis['action_type'] == 'create':
                    # Get the active sprint ID first
                    boards = self.jira_service.jira.boards(projectKeyOrID=project_code)
                    sprint_id = None
                    for board in boards:
                        sprints = self.jira_service.jira.sprints(board.id, state='active')
                        if sprints:
                            sprint_id = sprints[0].id
                            break
                    
                    # Create new tasks
                    for task in analysis['tasks']:
                        try:
                            # Get assignee's Jira username
                            assignee_info = USER_MAPPINGS.get(task['assignee'])
                            if not assignee_info:
                                continue
                                
                            # Create issue in Jira
                            issue_dict = {
                                'project': {'key': project_code},
                                'summary': task['title'],
                                'description': task['description'],
                                'issuetype': {'name': 'Task'},
                                'assignee': {'name': assignee_info['jira_username']},
                                self.jira_service.start_date_field: task['start_date'],
                                self.jira_service.end_date_field: task['end_date'],
                                'timetracking': {
                                    'originalEstimate': task['estimate'],
                                    'remainingEstimate': task['estimate']
                                }
                            }
                            
                            new_issue = self.jira_service.jira.create_issue(fields=issue_dict)
                            
                            # Add the issue to the active sprint
                            if sprint_id:
                                self.jira_service.jira.add_issues_to_sprint(sprint_id, [new_issue.key])
                            
                            created_tasks.append({
                                'key': new_issue.key,
                                'url': f"{JIRA_URL}/browse/{new_issue.key}",
                                'assignee': task['assignee'],
                                'title': task['title']
                            })
                            
                        except Exception as e:
                            print(f"Error creating task: {e}")
                            continue
                    
                elif analysis['action_type'] == 'update':
                    # Handle task updates
                    for update in analysis['updates']:
                        try:
                            issue = self.jira_service.jira.issue(update['key'])
                            update_dict = {}
                            
                            # Status update
                            if 'status' in update['fields']:
                                # Get transition ID for the desired status
                                transitions = self.jira_service.jira.transitions(issue)
                                for t in transitions:
                                    if t['to']['name'].lower() == update['fields']['status'].lower():
                                        self.jira_service.jira.transition_issue(issue, t['id'])
                                        break
                            
                            # End date update
                            if 'end_date' in update['fields']:
                                update_dict[self.jira_service.end_date_field] = update['fields']['end_date']
                            
                            # Estimate update
                            if 'estimate' in update['fields']:
                                update_dict['timetracking'] = {
                                    'originalEstimate': update['fields']['estimate'],
                                    'remainingEstimate': update['fields']['estimate']
                                }
                            
                            # Assignee update
                            if 'assignee' in update['fields']:
                                assignee_info = USER_MAPPINGS.get(update['fields']['assignee'])
                                if assignee_info:
                                    update_dict['assignee'] = {'name': assignee_info['jira_username']}
                            
                            # Apply updates if any
                            if update_dict:
                                issue.update(fields=update_dict)
                            
                            updated_tasks.append({
                                'key': issue.key,
                                'url': f"{JIRA_URL}/browse/{issue.key}",
                                'summary': issue.fields.summary,
                                'changes': list(update['fields'].keys()),
                                'reason': update['reason']
                            })
                            
                        except Exception as e:
                            print(f"Error updating task {update['key']}: {e}")
                            continue
                
                # Format response with created and updated tasks
                response = f"{analysis['response']}\n\n"
                
                if created_tasks:
                    response += "### Task creation:\n"
                    for task in created_tasks:
                        response += f"- [{task['key']}]({task['url']}): {task['title']} (Assigned to @{task['assignee']})\n"
                
                if updated_tasks:
                    response += "\n### Task updates:\n"
                    for task in updated_tasks:
                        changes = ", ".join(task['changes'])
                        response += f"- [{task['key']}]({task['url']}): {task['summary']}\n"
                        response += f"  • Updated fields: {changes}\n"
                        response += f"  • Reason: {task['reason']}\n"
                
                if analysis.get('reasoning'):
                    response += "\n## Reasoning:\n"
                    for aspect, explanation in analysis['reasoning'].items():
                        response += f"- {aspect.replace('_', ' ').title()}: {explanation}\n"
            else:
                response = analysis['response']
            
            # Send response
            self.driver.posts.create_post({
                'channel_id': channel_id,
                'message': response,
                'root_id': root_id
            })
            
        except Exception as e:
            print(f"Error handling bot mention: {str(e)}")
            print(f"Full error: {traceback.format_exc()}")
            
            try:
                # Use the same root_id logic for error messages
                root_id = post_data.get('root_id') or post_data.get('id')
                self.driver.posts.create_post({
                    'channel_id': channel_id,
                    'message': "Sorry, I encountered an error processing your question. Please try again.",
                    'root_id': root_id
                })
            except Exception as e2:
                print(f"Error sending error message: {str(e2)}")

if __name__ == "__main__":
    bot = ScrumBot()
    print("Bot started")
    bot.start() 
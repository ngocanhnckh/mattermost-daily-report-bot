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
    REPORT_TIME, REMINDER_INTERVAL, get_excluded_users,
    DAILY_REPORT_MESSAGE, TIMEZONE,
    AI_VALIDATION_ENABLED, OPENROUTER_API_KEY, SITE_URL, SITE_NAME,
    TEAM_NAME, REPORT_DEADLINE_TIME, get_user_mappings, get_channel_mappings,
    REMIND_TASK_MESSAGE, JIRA_URL
)
import ssl
from urllib.parse import urlparse
import json
import asyncio
from jira_service import JiraService
from message_analyzer import MessageAnalyzer
from twilio_service import TwilioService
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

        # Initialize Twilio service
        self.twilio_service = TwilioService()

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
                print(f"Deadline time: {REPORT_DEADLINE_TIME}")
                print(f"Last run date: {last_run_date}")
                print(f"Current date: {current_date}")
                
                # Check if it's time to run and we haven't run today
                target_hour, target_minute = REPORT_TIME.split(':')
                deadline_hour, deadline_minute = REPORT_DEADLINE_TIME.split(':')
                
                print(f"Comparing - Current: {current_hour}:{current_minute} vs Target: {target_hour}:{target_minute}")
                print(f"Time match: {current_hour == target_hour and current_minute == target_minute}")
                print(f"Date check: {current_date != last_run_date}")
                
                if (current_hour == target_hour and 
                    current_minute == target_minute and 
                    current_date != last_run_date):
                    
                    print(f"\n!!! TRIGGERING DAILY REPORT at {current_time} !!!")
                    self.send_daily_report()
                    last_run_date = current_date
                    print(f"Updated last run date to: {last_run_date}")
                else:
                    print("Not time for daily report yet")
                
                # Check if it's deadline time for AI-generated reports
                if (current_hour == deadline_hour and 
                    current_minute == deadline_minute):
                    print(f"\n!!! CHECKING FOR MISSING REPORTS at {current_time} !!!")
                    self._check_and_send_ai_reports()
                
                # Check reminders every minute
                self._check_reminders()
                print("Checked reminders")
                
                time.sleep(60)  # Check every minute
                
            except Exception as e:
                print(f"Error in scheduler loop: {str(e)}")
                print(f"Full error: {traceback.format_exc()}")
                time.sleep(60)

    def _check_and_send_ai_reports(self):
        """Check for users who haven't reported and send AI-generated reports."""
        try:
            print("\n=== Checking for Missing Reports ===")
            current_time = datetime.now(TIMEZONE)
            
            for channel_id, channel_info in self.channels.items():
                try:
                    channel_name = channel_info.get('name', '')
                    print(f"\nProcessing channel: {channel_name}")
                    
                    # Skip DM channels and Town Square
                    if '__' in channel_name or channel_name == '' or channel_name == 'town-square':
                        print(f"Skipping channel: {channel_name}")
                        continue
                    
                    # Get channel members
                    members = channel_info.get('members', [])
                    print(f"Channel members: {members}")
                    
                    # Get reported users for today
                    reported_users = set(self.db.get_today_reports(channel_id))
                    print(f"Users who have reported: {reported_users}")
                    
                    # Get the daily report post ID for this channel
                    if channel_id not in self.daily_report_posts:
                        print(f"No daily report post found for channel {channel_name}")
                        continue
                        
                    root_id = self.daily_report_posts[channel_id]['post_id']
                    
                    # Check each member who hasn't reported
                    for member in members:
                        if member in reported_users:
                            print(f"User {member} has already reported, skipping")
                            continue
                            
                        if member in get_excluded_users():
                            print(f"User {member} is excluded, skipping")
                            continue
                            
                        if member == BOT_USERNAME:
                            print(f"User {member} is the bot, skipping")
                            continue
                        
                        print(f"\nGenerating AI report for {member}")
                        
                        # Get user's recent messages
                        recent_messages = self._get_user_recent_messages(channel_id, member)
                        
                        # Get user's active tasks
                        user_info = get_user_mappings().get(member, {})
                        jira_username = user_info.get('jira_username', member)
                        jira_project = channel_info.get('jira_project')
                        
                        if not jira_project:
                            print(f"No Jira project found for channel {channel_name}")
                            continue
                            
                        active_tasks = self.jira_service.get_user_active_tasks(jira_username, jira_project)
                        recent_updates = self.jira_service.get_user_recent_updates(jira_username, jira_project)
                        
                        # Generate AI report
                        ai_report = self.message_analyzer.generate_report(
                            username=member,
                            messages=recent_messages,
                            active_tasks=active_tasks,
                            recent_updates=recent_updates
                        )
                        
                        if ai_report:
                            print(f"Sending AI-generated report for {member}")
                            self._send_ai_generated_report(channel_id, member, ai_report, root_id)
                        else:
                            print(f"Failed to generate AI report for {member}")
                            
                except Exception as e:
                    print(f"Error processing channel {channel_name}: {str(e)}")
                    print(f"Full error: {traceback.format_exc()}")
                    continue
                    
        except Exception as e:
            print(f"Error in _check_and_send_ai_reports: {str(e)}")
            print(f"Full error: {traceback.format_exc()}")

    def _check_reminders(self):
        """Check and send reminders for daily reports."""
        try:
            current_time = datetime.now(TIMEZONE)
            print(f"\n=== Checking Reminders at {current_time} ===")
            
            # Calculate reminder start time based on report time and interval
            report_hour, report_minute = map(int, REPORT_TIME.split(':'))
            reminder_interval = float(REMINDER_INTERVAL)
            
            # Create report time for today
            report_time = current_time.replace(hour=report_hour, minute=report_minute, second=0, microsecond=0)
            
            # Calculate when reminders should start
            reminder_start_time = report_time + timedelta(hours=reminder_interval)
            
            print(f"Report time: {report_time}")
            print(f"Reminder interval: {reminder_interval} hours")
            print(f"Reminder start time: {reminder_start_time}")
            print(f"Current time: {current_time}")
            print(f"Time difference: {current_time - reminder_start_time}")
            
            # If current time is before reminder start time, skip reminders
            if current_time < reminder_start_time:
                print(f"Current time {current_time} is before reminder start time {reminder_start_time}, skipping reminders")
                return
                
            print(f"Current time {current_time} is after reminder start time {reminder_start_time}, proceeding with reminders")
            
            # Check each channel
            for channel_id, channel_info in self.channels.items():
                channel_name = channel_info.get('name', '')
                print(f"\nChecking channel: {channel_name}")
                
                # Get channel members
                members = channel_info.get('members', [])
                print(f"Channel members: {members}")
                
                # Get reported users for today
                reported_users = set(self.db.get_today_reports(channel_id))
                print(f"Users who have reported: {reported_users}")
                
                # Check each member
                for member in members:
                    print(f"\nChecking member: {member}")
                    
                    # Skip if user has already reported
                    if member in reported_users:
                        print(f"User {member} has already reported, skipping")
                        continue
                        
                    # Skip if user is excluded
                    if member in get_excluded_users():
                        print(f"User {member} is excluded, skipping")
                        continue
                        
                    # Skip if user is the bot
                    if member == BOT_USERNAME:
                        print(f"User {member} is the bot, skipping")
                        continue
                    
                    # Send reminder
                    print(f"Sending reminder to {member}")
                    self._send_reminder_dm(member)
            
            # Check custom reminders (new section)
            print("\nChecking custom reminders...")
            for channel_id, reminders in self.pending_reminders.items():
                for username, reminder_info in list(reminders.items()):  # Use list to avoid modification during iteration
                    # Skip if this is not a custom reminder
                    if not isinstance(reminder_info, dict) or 'time' not in reminder_info:
                        continue
                        
                    reminder_time = reminder_info['time']
                    # Compare only hours and minutes
                    current_hm = current_time.replace(second=0, microsecond=0)
                    reminder_hm = reminder_time.replace(second=0, microsecond=0)
                    
                    if current_hm >= reminder_hm:
                        print(f"Sending custom reminder to {username}")
                        try:
                            # Create or get DM channel
                            user = self.driver.users.get_user_by_username(username)
                            dm_channel = self.driver.channels.create_direct_message_channel([self.bot_id, user['id']])
                            
                            # Send the reminder
                            self.driver.posts.create_post({
                                'channel_id': dm_channel['id'],
                                'message': f"🔔 **Reminder**: {reminder_info['message']}"
                            })
                            
                            # Remove the reminder after sending
                            del reminders[username]
                            print(f"Reminder sent and removed for {username}")
                        except Exception as e:
                            print(f"Error sending custom reminder to {username}: {e}")
                            print(traceback.format_exc())
                            
        except Exception as e:
            print(f"Error in _check_reminders: {e}")
            print(traceback.format_exc())

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
                    return

            # Debug the event structure
            print(f"Event keys: {event.keys() if isinstance(event, dict) else 'No keys (not a dict)'}")
            print(f"Event 'event' value: {event.get('event')}")
            print(f"Event 'data' value: {event.get('data')}")
            
            # Handle the initial hello event
            if event.get('event') == 'hello':
                print("Connected to websocket")
                return
            
            # Only proceed if we have data and it's a post event
            if event.get('event') == 'posted':
                print("Handling posted event")
                data = event.get('data', {})
                
                if isinstance(data.get('post'), str):
                    try:
                        post_data = json.loads(data['post'])
                        print(f"Parsed post data: {post_data}")
                        
                        if post_data['user_id'] != self.bot_id:  # Ignore bot's own messages
                            # Check if this is a DM channel by checking channel_type in event data
                            if data.get('channel_type') == 'D':
                                print(f"Received DM message from user {post_data['user_id']}")
                                await self._handle_dm(post_data)
                            # Check if bot is mentioned
                            elif f'@{BOT_USERNAME}' in post_data['message']:
                                await self._handle_bot_mention(post_data)
                            elif post_data.get('root_id'):  # This is a reply in a thread
                                self._handle_report_reply(post_data)
                            else:
                                self._handle_channel_message(post_data)
                    except json.JSONDecodeError as e:
                        print(f"Failed to parse post data: {e}")

        except Exception as e:
            print(f"Error in websocket event handler: {e}")
            print(f"Error type: {type(e)}")
            print(f"Traceback: {traceback.format_exc()}")

    async def _handle_task_actions(self, analysis: Dict, project_code: str) -> tuple[str, List[Dict], List[Dict]]:
        """Handle task creation and updates based on AI analysis.
        
        Args:
            analysis: The AI analysis result
            project_code: The Jira project code
            
        Returns:
            Tuple of (response message, created tasks, updated tasks)
        """
        print("\n=== Starting Task Actions ===")
        print(f"Project code: {project_code}")
        print(f"Analysis action type: {analysis.get('action_type')}")
        print(f"Number of updates to process: {len(analysis.get('updates', []))}")
        
        created_tasks = []
        updated_tasks = []
        
        if analysis.get('action_type') == 'create':
            print("\nProcessing task creation...")
            # Get the active sprint ID first
            boards = self.jira_service.jira.boards(projectKeyOrID=project_code)
            sprint_id = None
            for board in boards:
                sprints = self.jira_service.jira.sprints(board.id, state='active')
                if sprints:
                    sprint_id = sprints[0].id
                    break
            
            # Create new tasks
            for task in analysis.get('tasks', []):
                try:
                    print(f"\nCreating new task: {task['title']}")
                    # Get assignee's Jira username
                    assignee_info = get_user_mappings().get(task['assignee'])
                    if not assignee_info:
                        print(f"No assignee mapping found for {task['assignee']}, skipping task")
                        continue
                        
                    # Determine if this is a story or regular task
                    is_story = task['type'] == 'story'
                    print(f"Task type: {'Story' if is_story else 'Task'}")
                    
                    # Create issue in Jira
                    issue_dict = {
                        'project': {'key': project_code},
                        'summary': task['title'],
                        'description': task['description'],
                        'issuetype': {'name': 'Story' if is_story else 'Task'},
                        'assignee': {'name': assignee_info['jira_username']},
                        self.jira_service.start_date_field: task['start_date'],
                        self.jira_service.end_date_field: task['end_date'],
                        'timetracking': {
                            'originalEstimate': task['estimate'],
                            'remainingEstimate': task['estimate']
                        }
                    }
                    print(f"Creating Jira issue with fields: {issue_dict}")
                    
                    new_issue = self.jira_service.jira.create_issue(fields=issue_dict)
                    print(f"Created new issue: {new_issue.key}")
                    
                    # Add the issue to the active sprint
                    if sprint_id:
                        print(f"Adding {new_issue.key} to sprint {sprint_id}")
                        self.jira_service.jira.add_issues_to_sprint(sprint_id, [new_issue.key])
                    
                    created_task = {
                        'key': new_issue.key,
                        'url': f"{JIRA_URL}/browse/{new_issue.key}",
                        'assignee': task['assignee'],
                        'title': task['title'],
                        'type': task['type'],
                        'sub_tasks': []
                    }
                    
                    # If this is a story, create sub-tasks
                    if is_story and 'sub_tasks' in task:
                        print(f"Creating {len(task['sub_tasks'])} sub-tasks for {new_issue.key}")
                        for sub_task in task['sub_tasks']:
                            print(f"Creating sub-task: {sub_task['title']}")
                            # Get sub-task assignee's Jira username
                            sub_assignee_info = get_user_mappings().get(sub_task['assignee'])
                            if not sub_assignee_info:
                                print(f"No assignee mapping found for {sub_task['assignee']}, skipping sub-task")
                                continue
                                
                            # Create sub-task
                            sub_task_dict = {
                                'project': {'key': project_code},
                                'summary': sub_task['title'],
                                'description': sub_task['description'],
                                'issuetype': {'name': 'Sub-task'},
                                'parent': {'key': new_issue.key},
                                'assignee': {'name': sub_assignee_info['jira_username']},
                                self.jira_service.start_date_field: sub_task['start_date'],
                                self.jira_service.end_date_field: sub_task['end_date'],
                                'timetracking': {
                                    'originalEstimate': sub_task['estimate'],
                                    'remainingEstimate': sub_task['estimate']
                                }
                            }
                            
                            new_sub_task = self.jira_service.jira.create_issue(fields=sub_task_dict)
                            print(f"Created sub-task: {new_sub_task.key}")
                            
                            # Add sub-task to sprint
                            if sprint_id:
                                print(f"Adding sub-task {new_sub_task.key} to sprint {sprint_id}")
                                self.jira_service.jira.add_issues_to_sprint(sprint_id, [new_sub_task.key])
                            
                            created_task['sub_tasks'].append({
                                'key': new_sub_task.key,
                                'url': f"{JIRA_URL}/browse/{new_sub_task.key}",
                                'assignee': sub_task['assignee'],
                                'title': sub_task['title']
                            })
                    
                    created_tasks.append(created_task)
                    print(f"Successfully created task {new_issue.key} with {len(created_task['sub_tasks'])} sub-tasks")
                    
                except Exception as e:
                    print(f"Error creating task: {str(e)}")
                    print(f"Full error: {traceback.format_exc()}")
                    continue
                
        elif analysis.get('action_type') == 'update':
            print("\nProcessing task updates...")
            # Handle task updates
            for update in analysis.get('updates', []):
                try:
                    print(f"\nProcessing update for task {update['key']}:")
                    print(f"Action: {update['action']}")
                    print(f"Fields to update: {update.get('fields', {})}")
                    
                    if update['action'] == 'convert_to_story':
                        print("Converting task to story...")
                        # Get the original task
                        original_task = self.jira_service.jira.issue(update['key'])
                        print(f"Retrieved original task: {original_task.key}")
                        
                        # Create new story
                        story_dict = {
                            'project': {'key': project_code},
                            'summary': original_task.fields.summary,
                            'description': original_task.fields.description,
                            'issuetype': {'name': 'Story'},
                            'assignee': {'name': original_task.fields.assignee.name},
                            self.jira_service.start_date_field: getattr(original_task.fields, self.jira_service.start_date_field, None),
                            self.jira_service.end_date_field: getattr(original_task.fields, self.jira_service.end_date_field, None)
                        }
                        print(f"Creating new story with fields: {story_dict}")
                        
                        new_story = self.jira_service.jira.create_issue(fields=story_dict)
                        print(f"Created new story: {new_story.key}")
                        
                        # Create sub-tasks
                        created_sub_tasks = []
                        print(f"Creating {len(update['sub_tasks'])} sub-tasks for {new_story.key}")
                        for sub_task in update['sub_tasks']:
                            print(f"Creating sub-task: {sub_task['title']}")
                            # Get sub-task assignee's Jira username
                            sub_assignee_info = get_user_mappings().get(sub_task['assignee'])
                            if not sub_assignee_info:
                                print(f"No assignee mapping found for {sub_task['assignee']}, skipping sub-task")
                                continue
                                
                            # Create sub-task
                            sub_task_dict = {
                                'project': {'key': project_code},
                                'summary': sub_task['title'],
                                'description': sub_task['description'],
                                'issuetype': {'name': 'Sub-task'},
                                'parent': {'key': new_story.key},
                                'assignee': {'name': sub_assignee_info['jira_username']},
                                self.jira_service.start_date_field: sub_task['start_date'],
                                self.jira_service.end_date_field: sub_task['end_date'],
                                'timetracking': {
                                    'originalEstimate': sub_task['estimate'],
                                    'remainingEstimate': sub_task['estimate']
                                }
                            }
                            
                            new_sub_task = self.jira_service.jira.create_issue(fields=sub_task_dict)
                            print(f"Created sub-task: {new_sub_task.key}")
                            created_sub_tasks.append({
                                'key': new_sub_task.key,
                                'url': f"{JIRA_URL}/browse/{new_sub_task.key}",
                                'assignee': sub_task['assignee'],
                                'title': sub_task['title']
                            })
                        
                        # Delete the original task
                        print(f"Deleting original task {original_task.key}")
                        original_task.delete()
                        
                        updated_tasks.append({
                            'key': new_story.key,
                            'url': f"{JIRA_URL}/browse/{new_story.key}",
                            'summary': original_task.fields.summary,
                            'action': 'converted_to_story',
                            'original_key': update['key'],
                            'sub_tasks': created_sub_tasks,
                            'reason': update['reason']
                        })
                        print(f"Successfully converted {update['key']} to story {new_story.key}")
                        
                    else:  # Regular update
                        print("Performing regular update...")
                        issue = self.jira_service.jira.issue(update['key'])
                        print(f"Retrieved issue: {issue.key}")
                        update_dict = {}
                        
                        # Status update
                        if 'status' in update['fields']:
                            print(f"Updating status to: {update['fields']['status']}")
                            transitions = self.jira_service.jira.transitions(issue)
                            print(f"Available transitions: {[t['to']['name'] for t in transitions]}")
                            for t in transitions:
                                if t['to']['name'].lower() == update['fields']['status'].lower():
                                    print(f"Found matching transition ID: {t['id']}")
                                    self.jira_service.jira.transition_issue(issue, t['id'])
                                    print(f"Status updated successfully for {issue.key}")
                                    break
                        
                        # End date update
                        if 'end_date' in update['fields']:
                            print(f"Updating end date to: {update['fields']['end_date']}")
                            update_dict[self.jira_service.end_date_field] = update['fields']['end_date']
                        
                        # Estimate update
                        if 'estimate' in update['fields']:
                            print(f"Updating estimate to: {update['fields']['estimate']}")
                            update_dict['timetracking'] = {
                                'originalEstimate': update['fields']['estimate'],
                                'remainingEstimate': update['fields']['estimate']
                            }
                        
                        # Assignee update
                        if 'assignee' in update['fields']:
                            print(f"Updating assignee to: {update['fields']['assignee']}")
                            assignee_info = get_user_mappings().get(update['fields']['assignee'])
                            update_dict['assignee'] = {'name': assignee_info['jira_username']}
                            
                        
                        # Apply updates if any
                        if update_dict:
                            print(f"Applying updates to {issue.key}: {update_dict}")
                            issue.update(fields=update_dict)
                            print(f"Updates applied successfully to {issue.key}")
                        
                        updated_tasks.append({
                            'key': issue.key,
                            'url': f"{JIRA_URL}/browse/{issue.key}",
                            'summary': issue.fields.summary,
                            'changes': list(update['fields'].keys()),
                            'reason': update['reason']
                        })
                        print(f"Added task {issue.key} to updated_tasks list")
                    
                except Exception as e:
                    print(f"Error updating task {update['key']}: {str(e)}")
                    print(f"Full error: {traceback.format_exc()}")
                    continue
        
        print("\n=== Task Actions Summary ===")
        print(f"Created tasks: {len(created_tasks)}")
        print(f"Updated tasks: {len(updated_tasks)}")
        
        # Format response
        response = f"{analysis['response']}\n\n"
        
        if created_tasks:
            print("\nAdding created tasks to response...")
            response += "### Created Tasks:\n"
            for task in created_tasks:
                response += f"- [{task['key']}]({task['url']}): {task['title']} (Assigned to @{task['assignee']})\n"
                if task['type'] == 'story' and task['sub_tasks']:
                    response += "  Sub-tasks:\n"
                    for sub_task in task['sub_tasks']:
                        response += f"  - [{sub_task['key']}]({sub_task['url']}): {sub_task['title']} (Assigned to @{sub_task['assignee']})\n"
        
        if updated_tasks:
            print("\nAdding updated tasks to response...")
            response += "\n### Task Updates:\n"
            for task in updated_tasks:
                if task.get('action') == 'converted_to_story':
                    response += f"- Converted task {task['original_key']} to story [{task['key']}]({task['url']})\n"
                    response += f"  • Created sub-tasks:\n"
                    for sub_task in task['sub_tasks']:
                        response += f"    - [{sub_task['key']}]({sub_task['url']}): {sub_task['title']} (Assigned to @{sub_task['assignee']})\n"
                    response += f"  • Reason: {task['reason']}\n"
                else:
                    changes = ", ".join(task['changes'])
                    response += f"- [{task['key']}]({task['url']}): {task['summary']}\n"
                    response += f"  • Updated fields: {changes}\n"
                    response += f"  • Reason: {task['reason']}\n"
        
        if analysis.get('reasoning'):
            print("\nAdding reasoning to response...")
            response += "\n------------------------\n *Reasoning:*\n"
            for aspect, explanation in analysis['reasoning'].items():
                response += f"- {aspect.replace('_', ' ').title()}: {explanation}\n"
        
        print("\nTask actions completed successfully")
        return response, created_tasks, updated_tasks

    async def _handle_dm(self, post):
        """Handle direct messages to the bot."""
        try:
            user_id = post.get('user_id')
            message = post.get('message', '').strip()
            
            if not message:
                return
            
            # Get user's username
            user = self.driver.users.get_user(user_id)
            username = user['username']
            
            print(f"\n=== Handling DM from {username} ===")
            print(f"Message: {message}")
            
            # Get user's active tasks from all projects
            user_tasks = []
            for channel_id, channel_info in self.channels.items():
                jira_project = channel_info.get('jira_project')
                if jira_project:
                    user_info = get_user_mappings().get(username, {})
                    jira_username = user_info.get('jira_username', username)
                    tasks = self.jira_service.get_user_active_tasks(jira_username, jira_project)
                    user_tasks.extend(tasks)
            
            # Sort tasks by last updated
            user_tasks.sort(key=lambda x: x.get('updated', datetime.min), reverse=True)
            user_tasks = user_tasks[:100]  # Limit to 100 most recent tasks
            
            # Get recent messages from all channels
            recent_messages = self._get_user_all_channels_messages(username)
            
            # Get channel members for context
            channel_members = {}
            for channel_id, channel_info in self.channels.items():
                if username in channel_info.get('members', []):
                    for member in channel_info.get('members', []):
                        if member not in get_excluded_users() and member != BOT_USERNAME:
                            channel_members[member] = get_user_mappings().get(member, {})
            
            # Format tasks for analysis
            formatted_tasks = []
            for task in user_tasks:
                formatted_task = {
                    'key': task.get('key', ''),
                    'summary': task.get('summary', ''),
                    'status': task.get('status', ''),
                    'end_date': task.get('end_date'),
                    'start_date': task.get('start_date'),
                    'assignee': task.get('assignee', ''),
                    'assignee_display_name': task.get('assignee_display_name', ''),
                    'url': task.get('url', ''),
                    'original_estimate': task.get('original_estimate', ''),
                    'updated': task.get('updated', datetime.min)
                }
                formatted_tasks.append(formatted_task)
            
            # Analyze the message with full context
            analysis = self.message_analyzer.analyze_question(
                question=message,
                prior_messages=recent_messages,
                active_tasks=formatted_tasks,
                channel_members=channel_members
            )
            
            # Handle task actions if needed
            if analysis.get('needs_action'):
                # Get the project code from the user's most recent task
                project_code = None
                if user_tasks:
                    project_code = user_tasks[0]['key'].split('-')[0]
                
                if project_code:
                    response, _, _ = await self._handle_task_actions(analysis, project_code)
                else:
                    response = analysis['response']
            else:
                response = analysis['response']
            
            # Send response
            await self._send_dm(user_id, response)
            
        except Exception as e:
            print(f"Error handling DM: {e}")
            print(f"Full error: {traceback.format_exc()}")
            await self._send_dm(user_id, "I encountered an error processing your message. Please try again.")

    async def _send_dm(self, user_id: str, message: str):
        """Send a direct message to a user."""
        try:
            # Create DM channel first
            dm_channel = self.driver.channels.create_direct_message_channel([self.bot_id, user_id])
            
            # Send message to the DM channel
            result = self.driver.posts.create_post({
                'channel_id': dm_channel['id'],
                'message': message
            })
            
            if result:
                print(f"Successfully sent DM to user {user_id}")
            else:
                print(f"Failed to send DM to user {user_id}")
                
        except Exception as e:
            print(f"Error sending DM: {e}")
            print(f"Full error: {traceback.format_exc()}")

    def _get_user_all_channels_messages(self, username: str) -> List[str]:
        """Get recent messages from all channels the user is in."""
        print(f"\n=== Getting Recent Messages from All Channels for {username} ===")
        
        try:
            # Get all channels the user is in
            user_channels = []
            for channel_id, channel_info in self.channels.items():
                if username in channel_info.get('members', []):
                    user_channels.append((channel_id, channel_info.get('name', 'Unknown')))
            
            if not user_channels:
                print(f"No channels found for user {username}")
                return []
            
            print(f"Found {len(user_channels)} channels for user {username}")
            
            # Get recent messages from each channel
            formatted_messages = []
            for channel_id, channel_name in user_channels:
                try:
                    # Skip DM channels and Town Square
                    if '__' in channel_name or channel_name == '' or channel_name == 'town-square':
                        print(f"Skipping channel: {channel_name}")
                        continue
                        
                    # Add channel separator
                    formatted_messages.append(f"\nNow showing messages for channel {channel_name}")
                    
                    # Get channel messages
                    posts = self.driver.posts.get_posts_for_channel(channel_id)
                    
                    if posts and 'posts' in posts:
                        # Collect all messages (except bot messages) with their timestamps
                        channel_messages = []
                        for post_id, post in posts['posts'].items():
                            if post.get('user_id') != self.bot_id:  # Skip bot messages
                                try:
                                    # Get the username for the message author
                                    user = self.driver.users.get_user(post.get('user_id', ''))
                                    poster_username = user['username']
                                except:
                                    poster_username = 'Unknown User'
                                
                                channel_messages.append({
                                    'username': poster_username,
                                    'message': post.get('message', ''),
                                    'create_at': post.get('create_at', 0)
                                })
                        
                        # Sort messages by timestamp (newest first) and take top 10
                        channel_messages.sort(key=lambda x: x['create_at'], reverse=True)
                        channel_messages = channel_messages[:10]
                        
                        if channel_messages:
                            # Format messages with usernames
                            formatted_messages.extend([
                                f"@{msg['username']}: {msg['message']}"
                                for msg in channel_messages
                            ])
                        else:
                            formatted_messages.append("No recent messages in this channel")
                    else:
                        formatted_messages.append("No messages found in this channel")
                        
                except Exception as e:
                    print(f"Error getting messages for channel {channel_name}: {e}")
                    formatted_messages.append(f"Error retrieving messages for channel {channel_name}")
                    continue
            
            print(f"Found messages from {len(user_channels)} channels")
            print(formatted_messages)
            return formatted_messages
            
        except Exception as e:
            print(f"Error getting all channel messages: {e}")
            print(f"Full error: {traceback.format_exc()}")
            return []

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
            channel_mapping = get_channel_mappings().get(channel_name, {})
            project_code = channel_mapping.get('jira_project')
            
            if not project_code:
                print(f"No Jira project mapping found for channel {channel_name}")
                return
            
            # Get channel members with their details
            channel_members = {
                member: get_user_mappings().get(member, {})
                for member in channel_info.get('members', [])
                if member not in get_excluded_users() and member != BOT_USERNAME
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
        
        # Get Jira project code from channel mappings
        channel_mappings = get_channel_mappings()
        channel_name = channel['name']
        print(f"Processing channel: {channel_name}")
        
        # Try to get project code from channel mappings
        jira_project = None
        if channel_name in channel_mappings:
            jira_project = channel_mappings[channel_name].get('jira_project')
            print(f"Found Jira project code for channel {channel_name}: {jira_project}")
        else:
            print(f"No Jira mapping found for channel {channel_name}")
            
        # Store channel info regardless of Jira project code
        self.channels[channel_id] = {
            'name': channel_name,
            'members': member_usernames,
            'jira_project': jira_project
        }
        print(f"Updated channel info for {channel_name} with {len(member_usernames)} members")

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
                    jira_project = channel_info.get('jira_project')
                    if not jira_project:
                        print(f"No Jira project code found for channel {channel_name}, skipping")
                        continue
                    
                    print(f"Found Jira project mapping: {channel_name} -> {jira_project}")
                    print("\nCalling _format_daily_report_message...")
                    
                    # Format the message and get tagged users using the new method
                    message, tagged_users = self._format_daily_report_message(channel_id, channel_name)
                    print(f"\nMessage formatted. Tagged users: {tagged_users}")
                    
                    if tagged_users:
                        print("\nSending message to channel...")
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
                        self.db.add_bot_request(channel_id, channel_name, tagged_users)
                        print(f"Recorded report request for {len(tagged_users)} users in {channel_name}")
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
            channel_mappings = get_channel_mappings()
            jira_project = channel_mappings.get(channel_name, {}).get('jira_project')
            print(f"\nGetting tasks for channel {channel_name} (Jira: {jira_project})")

            if jira_project and self.jira_service.enabled:
                # First validate and update sprint tasks
                channel_members = {
                    member: get_user_mappings().get(member, {}).get('jira_username', member)
                    for member in self.channels[channel_id].get('members', [])
                    if member not in get_excluded_users() and member != BOT_USERNAME
                }
                validation_result = self.jira_service.validate_and_update_sprint_tasks(jira_project, channel_members)
                if validation_result.get('updated', 0) > 0:
                    print(f"Updated {validation_result['updated']} tasks with missing fields")
                    for task in validation_result.get('tasks', []):
                        print(f"- {task['key']}: Updated {', '.join(task['updated_fields'])}")

                # Get all active tasks for the project
                jql = (
                    f"project = '{jira_project}' "
                    f"AND status IN ('To Do', 'In Progress') "
                    f"AND sprint IN openSprints()"
                )
                all_tasks = self.jira_service.jira.search_issues(jql)
                
                # Group tasks by assignee
                tasks_by_assignee = {}
                for issue in all_tasks:
                    if issue.fields.assignee:
                        assignee = issue.fields.assignee.name
                        if assignee not in tasks_by_assignee:
                            tasks_by_assignee[assignee] = []
                        tasks_by_assignee[assignee].append(issue)

                for member in self.channels[channel_id].get('members', []):
                    if member in get_excluded_users() or member == BOT_USERNAME:
                        continue

                    # Get user's Jira mapping
                    user_info = get_user_mappings().get(member, {})
                    jira_username = user_info.get('jira_username', member)
                    
                    # Get user's tasks
                    user_tasks = tasks_by_assignee.get(jira_username, [])
                    
                    # Sort tasks by status and end date
                    in_progress_tasks = []
                    todo_tasks = []
                    
                    for task in user_tasks:
                        task_info = {
                            'key': task.key,
                            'summary': task.fields.summary,
                            'status': task.fields.status.name,
                            'end_date': datetime.strptime(getattr(task.fields, self.jira_service.end_date_field, None), '%Y-%m-%d') if getattr(task.fields, self.jira_service.end_date_field, None) else None,
                            'start_date': datetime.strptime(getattr(task.fields, self.jira_service.start_date_field, None), '%Y-%m-%d') if getattr(task.fields, self.jira_service.start_date_field, None) else None,
                            'priority': task.fields.priority.name if task.fields.priority else 'Medium',
                            'url': f"{JIRA_URL}/browse/{task.key}"
                        }
                        
                        if task.fields.status.name == 'In Progress':
                            in_progress_tasks.append(task_info)
                        else:
                            todo_tasks.append(task_info)

                    # Sort tasks by end date and priority
                    for task_list in [in_progress_tasks, todo_tasks]:
                        task_list.sort(key=lambda x: (
                            x['end_date'] if x['end_date'] else datetime.max,
                            x['priority'] if x['priority'] else 'Medium',
                            x['key']
                        ))

                    if user_tasks:  # Only tag users with active tasks
                        tagged_users.append(member)
                        user_mention = f"@{member}"
                        task_mentions = []
                        
                        # Start user section
                        user_section = [f"### {user_mention}'s Tasks and Focus"]
                        
                        # Add active tasks section if there are any
                        if in_progress_tasks or todo_tasks:
                            user_section.append("\n#### 📋 Please Update Tasks:")
                            
                            # Add in-progress tasks first
                            for task in in_progress_tasks[:3]:  # Increased from 2 to 3 tasks
                                urgent = ""
                                if task['end_date']:
                                    if task['end_date'].date() <= (datetime.now(TIMEZONE) + timedelta(days=1)).date():
                                        urgent = "🚨 **URGENT**"
                                task_mentions.append(
                                    f"- [{task['key']}]({task['url']}): {task['summary']} "
                                    f"({task['status']}) {urgent}"
                                )
                            
                            # Add to-do tasks based on logic
                            remaining_slots = 3 - len(task_mentions)  # Increased from 2 to 3
                            if remaining_slots > 0:
                                # First, add tasks close to deadline
                                for task in todo_tasks:
                                    if remaining_slots <= 0:
                                        break
                                    if task['end_date'] and task['end_date'].date() <= (datetime.now(TIMEZONE) + timedelta(days=4)).date():
                                        urgent = "🚨 **URGENT**" if task['end_date'].date() <= (datetime.now(TIMEZONE) + timedelta(days=1)).date() else ""
                                        task_mentions.append(
                                            f"- [{task['key']}]({task['url']}): {task['summary']} "
                                            f"({task['status']}) {urgent}"
                                        )
                                        remaining_slots -= 1
                                
                                # Then, add tasks that started recently but still in To Do
                                if remaining_slots > 0:
                                    for task in todo_tasks:
                                        if remaining_slots <= 0:
                                            break
                                        if task['start_date'] and task['start_date'].date() >= (datetime.now(TIMEZONE) - timedelta(days=2)).date():
                                            task_mentions.append(
                                                f"- [{task['key']}]({task['url']}): {task['summary']} "
                                                f"({task['status']})"
                                            )
                                            remaining_slots -= 1
                            
                            if task_mentions:
                                user_section.extend(task_mentions)
                            
                        # Add focus suggestion based on task count and status
                        user_section.extend([
                            "\n#### 💡 Today's Focus:",
                        ])
                        
                        if len(in_progress_tasks) == 0:
                            user_section.append("You don't have any tasks in progress. Please pick up tasks from your To Do list, prioritizing those with upcoming deadlines.")
                            # Add recommended tasks from todo list
                            if todo_tasks:
                                user_section.append("\nRecommended tasks to pick up:")
                                for task in todo_tasks[:3]:  # Show top 3 recommended tasks
                                    urgent = "🚨 **URGENT**" if task['end_date'] and task['end_date'].date() <= (datetime.now(TIMEZONE) + timedelta(days=1)).date() else ""
                                    user_section.append(f"- [{task['key']}]({task['url']}): {task['summary']} {urgent}")
                        elif len(in_progress_tasks) == 1:
                            user_section.append("You have 1 task in progress. Consider picking up additional tasks from your To Do list, especially those with upcoming deadlines.")
                            # Add recommended tasks from todo list
                            if todo_tasks:
                                user_section.append("\nRecommended tasks to pick up:")
                                for task in todo_tasks[:2]:  # Show top 2 recommended tasks
                                    urgent = "🚨 **URGENT**" if task['end_date'] and task['end_date'].date() <= (datetime.now(TIMEZONE) + timedelta(days=1)).date() else ""
                                    user_section.append(f"- [{task['key']}]({task['url']}): {task['summary']} {urgent}")
                        elif len(in_progress_tasks) == 2:
                            user_section.append("You have 2 tasks in progress. You can take on one more task if needed.")
                            # Add recommended tasks from todo list
                            if todo_tasks:
                                user_section.append("\nRecommended tasks to pick up:")
                                for task in todo_tasks[:1]:  # Show top 1 recommended task
                                    urgent = "🚨 **URGENT**" if task['end_date'] and task['end_date'].date() <= (datetime.now(TIMEZONE) + timedelta(days=1)).date() else ""
                                    user_section.append(f"- [{task['key']}]({task['url']}): {task['summary']} {urgent}")
                        else:
                            urgent_tasks = [t for t in in_progress_tasks if t['end_date'] and t['end_date'].date() <= (datetime.now(TIMEZONE) + timedelta(days=1)).date()]
                            if urgent_tasks:
                                user_section.append(f"You have {len(in_progress_tasks)} tasks in progress. Focus on completing the urgent tasks first:")
                                for task in urgent_tasks:
                                    user_section.append(f"- [{task['key']}]({task['url']}): {task['summary']} 🚨 **URGENT**")
                            else:
                                user_section.append(f"You have {len(in_progress_tasks)} tasks in progress. Focus on completing tasks in order of priority and deadline:")
                                # Show top 2 in-progress tasks to focus on
                                for task in in_progress_tasks[:2]:
                                    user_section.append(f"- [{task['key']}]({task['url']}): {task['summary']}")
                        
                        user_task_mentions.append("\n".join(user_section))

            # Construct the final message
            message = (
                f"## 🔔 **Daily Scrum Report for {date_str}**\n\n"
                f"{DAILY_REPORT_MESSAGE}"
                f"Good morning {' '.join(f'@{user}' for user in tagged_users)}! "
                f"Here are your tasks and suggested focus for today:\n\n"
            )
            
            if user_task_mentions:
                message += "\n".join(user_task_mentions) + "\n\n"
            
            print(f"Daily Task Suggest Message: {message}")
            
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
                        user_pending_channels.append({
                            'name': channel_name,
                            'link': thread_link
                        })
            
            # Only send reminder if there are pending channels
            if user_pending_channels:
                # Add date and thread links to the reminder message
                message = (
                    f"{REMIND_TASK_MESSAGE}"
                    f"⏰ **Daily Report Reminder for {date_str}**\n\n"
                    f"You still need to submit your daily report in the following channels:\n"
                )
                
                for channel in user_pending_channels:
                    message += f"• [{channel['name']}]({channel['link']})\n"
                
                # Send reminder message
                self.driver.posts.create_post({
                    'channel_id': dm_channel['id'],
                    'message': message
                })
                print(f"Reminder sent to {username} for {len(user_pending_channels)} pending channels")

                # Send SMS reminder if enabled and user has a phone number
                user_info = get_user_mappings().get(username, {})
                if user_info.get('phone'):
                    # Send SMS for each pending channel
                    for channel in user_pending_channels:
                        self.twilio_service.send_sms(
                            to_number=user_info['phone'],
                            username=username,
                            channel_name=channel['name'],
                            thread_link=channel['link']
                        )
            else:
                print(f"No pending channels to remind {username} about")
                
        except Exception as e:
            print(f"Error sending reminder to {username}: {str(e)}")
            print(f"Full error: {traceback.format_exc()}")

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
                f"{REMIND_TASK_MESSAGE}\n\n"
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

    async def _handle_bot_mention(self, post_data):
        try:
            print("\n=== Handling Bot Mention ===")
            # Get the root_id - if this is a thread reply, use the parent thread's id
            root_id = post_data.get('root_id') or post_data.get('id')
            print(f"Root ID: {root_id}")
            
            channel_id = post_data['channel_id']
            user_id = post_data['user_id']
            message = post_data['message'].replace(f'@{BOT_USERNAME}', '').strip()  # Remove bot mention
            print(f"Channel ID: {channel_id}")
            print(f"User ID: {user_id}")
            print(f"Message: {message}")
            
            # Get channel info
            channel_info = self.channels.get(channel_id, {})
            channel_name = channel_info.get('name', '')
            print(f"Channel name: {channel_name}")
            
            # Get Jira project code
            channel_mapping = get_channel_mappings().get(channel_name, {})
            project_code = channel_mapping.get('jira_project')
            print(f"Project code: {project_code}")
            
            if not project_code:
                print("No project code found for channel, sending error message")
                self.driver.posts.create_post({
                    'channel_id': channel_id,
                    'message': "Sorry, this channel is not configured with a Jira project.",
                    'root_id': root_id
                })
                return
            
            # Get user info
            username = self.driver.users.get_user(user_id)['username']
            print(f"Username: {username}")
            
            # Get prior messages
            print("\nGathering prior messages...")
            posts = self.driver.posts.get_posts_for_channel(channel_id)
            prior_messages = []
            
            # Check if this is a thread reply
            is_thread_reply = bool(post_data.get('root_id'))
            print(f"Is thread reply: {is_thread_reply}")
            
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
                        
                # Limit to x messages
                if len(prior_messages) >= 30:
                    break
            
            print(f"Gathered {len(prior_messages)} prior messages")
            
            # Get recently updated tasks for this project
            active_tasks = []
            if project_code:
                print("\nGetting recent project tasks...")
                active_tasks = self.jira_service.get_recent_project_tasks(project_code)
                print(f"Found {len(active_tasks)} active tasks")
            
            # Get channel members with their details
            channel_members = {
                member: get_user_mappings().get(member, {})
                for member in channel_info.get('members', [])
                if member not in get_excluded_users() and member != BOT_USERNAME
            }
            print(f"\nChannel members: {len(channel_members)}")
            
            # Analyze the question with username in the message
            print("\nAnalyzing question...")
            analysis = self.ai_validator.analyze_question(
                f"@{username}: {message}",
                prior_messages,
                active_tasks,
                channel_members
            )
            
            print("\nAnalysis result:")
            print(f"Needs action: {analysis.get('needs_action')}")
            print(f"Action type: {analysis.get('action_type')}")
            print(f"Number of tasks: {len(analysis.get('tasks', []))}")
            print(f"Number of updates: {len(analysis.get('updates', []))}")
            
            if analysis['needs_action']:
                if analysis['action_type'] == 'reminder':
                    print("\nHandling reminder request...")
                    # Handle reminder request
                    reminder_info = analysis.get('reminder', {})
                    if reminder_info and 'time' in reminder_info:
                        # Initialize channel's pending reminders if not exists
                        if channel_id not in self.pending_reminders:
                            self.pending_reminders[channel_id] = {}
                            
                        # Store the reminder
                        target_username = reminder_info.get('username', username)  # Default to sender if no target specified
                        reminder_content = {
                            'time': datetime.fromisoformat(reminder_info['time']),
                            'message': reminder_info['message']
                        }
                        self.pending_reminders[channel_id][target_username] = reminder_content
                        print(f"Reminder set for {target_username} at {reminder_content['time']}")
                        
                        # Send confirmation
                        self.driver.posts.create_post({
                            'channel_id': channel_id,
                            'message': analysis['response'],
                            'root_id': root_id
                        })
                        print(f"Reminder confirmation sent to {target_username}")
                        
                elif project_code:  # Handle other actions only if project code exists
                    print("\nHandling task actions...")
                    response, created_tasks, updated_tasks = await self._handle_task_actions(analysis, project_code)
                    print(f"\nTask actions completed:")
                    print(f"Created tasks: {len(created_tasks)}")
                    print(f"Updated tasks: {len(updated_tasks)}")
                    
                    # Send response
                    self.driver.posts.create_post({
                        'channel_id': channel_id,
                        'message': response,
                        'root_id': root_id
                    })
                    print("Response sent to channel")
                else:
                    # Send response for non-project channels
                    print("\nNo project code found, sending error message")
                    self.driver.posts.create_post({
                        'channel_id': channel_id,
                        'message': "Sorry, this channel is not configured with a Jira project.",
                        'root_id': root_id
                    })
                
                print(f"Response sent to channel {channel_name}")
                
            else:
                print("\nNo action needed, sending informational response")
                response = analysis['response']
                
                # Send response
                self.driver.posts.create_post({
                    'channel_id': channel_id,
                    'message': response,
                    'root_id': root_id
                })
                
                print(f"Response sent to channel {channel_name}")
            
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
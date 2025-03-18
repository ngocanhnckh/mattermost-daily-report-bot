from jira import JIRA
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from config import JIRA_URL, JIRA_TOKEN, USER_MAPPINGS
import traceback
import json
from ai_validator import AIValidator
import re

logger = logging.getLogger(__name__)

class JiraService(AIValidator):
    def __init__(self, api_key: str, site_url: str = "", site_name: str = "", enabled: bool = True):
        """Initialize Jira service and AI validator"""
        super().__init__(api_key, site_url, site_name, enabled)
        
        if not JIRA_URL or not JIRA_TOKEN:
            logger.warning("Jira credentials not configured")
            self.enabled = False
            return
            
        try:
            self.jira = JIRA(server=JIRA_URL, token_auth=JIRA_TOKEN)
            
            # Get custom field mapping
            print("Getting Jira field mappings...")
            fields = self.jira.fields()
            self.end_date_field = None
            self.original_estimate_field = None
            self.start_date_field = None
            
            for field in fields:
                print(f"Found field: {field['name']} (ID: {field['id']})")  # Debug output
                if field['name'] == 'End date':
                    self.end_date_field = field['id']
                    print(f"Found End date field: {self.end_date_field}")
                elif field['name'] == 'Original Estimate':
                    self.original_estimate_field = field['id']
                    print(f"Found Original Estimate field: {self.original_estimate_field}")
                elif field['name'] == 'Start date':
                    self.start_date_field = field['id']
                    print(f"Found Start date field: {self.start_date_field}")
            
            # Log warnings for any missing fields
            if not self.end_date_field:
                print("WARNING: Could not find 'End date' field in Jira")
            if not self.original_estimate_field:
                print("WARNING: Could not find 'Original Estimate' field in Jira")
            if not self.start_date_field:
                print("WARNING: Could not find 'Start date' field in Jira")
            
            logger.info("Jira service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Jira service: {e}")
            self.enabled = False
    
    def get_user_active_tasks(self, jira_username: str, project_code: str) -> List[Dict]:
        """Get active tasks for a user in a project"""
        print(f"\n=== Getting Jira tasks for {jira_username} in {project_code} ===")
        
        if not self.enabled:
            print("Jira service is not enabled, skipping")
            return []
            
        try:
            jql = (
                f"project = {project_code} "
                f"AND assignee = {jira_username} "
                f"AND status IN ('To Do', 'In Progress') "
                f"AND sprint IN openSprints()"
            )
            print(f"Executing JQL: {jql}")
            
            issues = self.jira.search_issues(jql)
            print(f"Found {len(issues)} issues")
            
            tasks = []
            for issue in issues:
                end_date = None
                if hasattr(issue.fields, self.end_date_field) and getattr(issue.fields, self.end_date_field):
                    end_date = datetime.strptime(getattr(issue.fields, self.end_date_field), '%Y-%m-%d')
                
                task = {
                    'key': issue.key,
                    'summary': issue.fields.summary,
                    'status': issue.fields.status.name,
                    'end_date': end_date,
                    'url': f"{JIRA_URL}/browse/{issue.key}"
                }
                tasks.append(task)
                print(f"Added task: {task['key']} - {task['summary']} ({task['status']})")
            
            return tasks
            
        except Exception as e:
            print(f"Error fetching Jira tasks: {str(e)}")
            print(f"Full error: {traceback.format_exc()}")
            return []

    def get_user_recent_updates(self, jira_username: str, project_code: str) -> List[Dict]:
        """Get tasks that were updated by the user in the last 2 days."""
        print(f"\n=== Getting recent Jira updates for {jira_username} in {project_code} ===")
        
        if not self.enabled:
            print("Jira service is not enabled, skipping")
            return []
            
        try:
            # Calculate the start of yesterday
            start_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
            
            # Query for issues assigned to the user that were updated recently
            jql = (
                f"project = {project_code} "
                f"AND assignee = {jira_username} "
                f"AND updated >= '{start_date}' "
                f"ORDER BY updated DESC"
            )
            print(f"Executing JQL for recent updates: {jql}")
            
            issues = self.jira.search_issues(
                jql,
                expand='changelog'  # Include changelog to see status changes
            )
            print(f"Found {len(issues)} recently updated issues")
            
            updates = []
            for issue in issues:
                try:
                    # Get the changelog
                    changelog = issue.changelog
                    recent_changes = []
                    
                    # Look for status changes in the last 2 days
                    for history in changelog.histories:
                        history_date = datetime.strptime(history.created[:10], '%Y-%m-%d')
                        if history_date.date() >= (datetime.now() - timedelta(days=2)).date():
                            for item in history.items:
                                if item.field == 'status':  # Focus on status changes
                                    recent_changes.append({
                                        'field': item.field,
                                        'from': item.fromString,
                                        'to': item.toString,
                                        'date': history.created
                                    })
                    
                    if recent_changes:
                        updates.append({
                            'key': issue.key,
                            'summary': issue.fields.summary,
                            'current_status': issue.fields.status.name,
                            'changes': recent_changes,
                            'url': f"{self.jira._options['server']}/browse/{issue.key}"
                        })
                        print(f"Added task with updates: {issue.key} - {issue.fields.summary}")
                        for change in recent_changes:
                            print(f"  - {change['field']}: {change['from']} -> {change['to']}")
                            
                except Exception as e:
                    print(f"Error processing changelog for {issue.key}: {e}")
                    continue
            
            return updates
            
        except Exception as e:
            print(f"Error fetching Jira updates: {str(e)}")
            print(f"Full error: {traceback.format_exc()}")
            return []

    def validate_and_update_sprint_tasks(self, project_code: str, channel_members: Dict[str, str]) -> Dict:
        """Validate and update sprint tasks before daily report."""
        print(f"\n{'='*50}")
        print(f"=== Validating Sprint Tasks for Project {project_code} ===")
        
        if not self.enabled:
            print("Jira service is not enabled, skipping")
            return {}
        
        try:
            # Step 1: Get all tasks in active sprint and sprint info
            print("\nStep 1: Fetching active sprint tasks...")
            jql = (
                f"project = {project_code} "
                f"AND sprint in openSprints()"
            )
            issues = self.jira.search_issues(jql, maxResults=1000)
            print(f"Found {len(issues)} tasks in active sprint")
            
            # Get active sprint start date
            boards = self.jira.boards(projectKeyOrID=project_code)
            sprint_start_date = None
            for board in boards:
                sprints = self.jira.sprints(board.id, state='active')
                if sprints:
                    sprint = sprints[0]  # Get the first active sprint
                    sprint_start_date = sprint.startDate.split('T')[0] if hasattr(sprint, 'startDate') else None
                    print(f"Found active sprint start date: {sprint_start_date}")
                    break

            # Step 2: Filter tasks missing required fields
            print("\nStep 2: Checking for missing fields...")
            tasks_needing_update = []
            for issue in issues:
                # Debug print the entire issue fields
                print(f"\n=== Debug Issue {issue.key} ===")
                print("All fields available:")
                for field_name in dir(issue.fields):
                    if not field_name.startswith('_'):  # Skip internal attributes
                        try:
                            value = getattr(issue.fields, field_name)
                            print(f"{field_name}: {value}")
                        except Exception as e:
                            print(f"Error getting {field_name}: {e}")
                
                # Debug print timetracking specifically
                if hasattr(issue.fields, 'timetracking'):
                    print("\nTimetracking details:")
                    print(f"Raw timetracking: {issue.fields.timetracking}")
                    for attr in dir(issue.fields.timetracking):
                        if not attr.startswith('_'):
                            try:
                                value = getattr(issue.fields.timetracking, attr)
                                print(f"timetracking.{attr}: {value}")
                            except Exception as e:
                                print(f"Error getting timetracking.{attr}: {e}")

                missing_fields = []
                
                # Check End date
                if not hasattr(issue.fields, self.end_date_field) or not getattr(issue.fields, self.end_date_field):
                    missing_fields.append('End date')
                
                # Check Start date
                if not hasattr(issue.fields, self.start_date_field) or not getattr(issue.fields, self.start_date_field):
                    missing_fields.append('Start date')
                    
                # Check assignee
                if not hasattr(issue.fields, 'assignee') or not issue.fields.assignee:
                    missing_fields.append('assignee')
                    
                # Check Original Estimate
                if (not hasattr(issue.fields, 'timetracking') or 
                    not issue.fields.timetracking or 
                    not hasattr(issue.fields.timetracking, 'originalEstimate') or 
                    not issue.fields.timetracking.originalEstimate):
                    missing_fields.append('Original Estimate')
                    print(f"Task {issue.key} missing Original Estimate")
                
                if missing_fields:
                    # Get actual field values from Jira
                    task_info = {
                        'key': issue.key,
                        'summary': issue.fields.summary,
                        'missing_fields': missing_fields,
                    }
                    
                    # Add all available fields for context
                    for field_name in dir(issue.fields):
                        if not field_name.startswith('_'):
                            try:
                                value = getattr(issue.fields, field_name)
                                if value is not None:
                                    task_info[field_name] = str(value)
                            except:
                                continue
                    
                    tasks_needing_update.append(task_info)
                    print(f"Task {issue.key} missing fields: {', '.join(missing_fields)}")
                    print(f"Task info collected: {json.dumps(task_info, indent=2)}")
            
            print(f"Found {len(tasks_needing_update)} tasks needing updates")
            
            if not tasks_needing_update:
                print("No tasks need updating")
                return {'updated': 0, 'tasks': []}
            
            # Step 3: Get AI suggestions for updates
            print("\nStep 3: Getting AI suggestions...")
            
            if not self.client:  # Check if AI client is available
                print("AI client not initialized, skipping task updates")
                return {'error': 'AI client not available', 'updated': 0, 'tasks': []}
            
            # Format user information with their roles/expertise
            user_info = []
            for matt_username, jira_username in channel_members.items():
                user_info_dict = USER_MAPPINGS.get(matt_username, {})
                bio = user_info_dict.get('bio', '')
                user_info.append(f"- {matt_username} ({jira_username}): {bio}")
            
            user_info_str = "\n".join(user_info)
            
            # Format tasks information based on actual Jira fields
            tasks_info = []
            for task in tasks_needing_update:
                # Get the original issue for this task
                issue = self.jira.issue(task['key'])
                
                # Create a clean, readable task description
                task_details = [
                    f"- {task['key']}: {task['summary']}",
                    f"  Priority: {issue.fields.priority.name if hasattr(issue.fields, 'priority') and issue.fields.priority else 'Not set'}",
                    f"  Description: {issue.fields.description if hasattr(issue.fields, 'description') and issue.fields.description else 'No description'}",
                    f"  Missing fields: {', '.join(task['missing_fields'])}",
                    f"  Status: {issue.fields.status.name}",
                ]
                
                # Add assignee info
                if hasattr(issue.fields, 'assignee') and issue.fields.assignee:
                    task_details.append(f"  Current assignee: {issue.fields.assignee.displayName}")
                
                # Add start date if available
                if hasattr(issue.fields, self.start_date_field):
                    start_date = getattr(issue.fields, self.start_date_field)
                    if start_date:
                        task_details.append(f"  Start date: {start_date}")
                
                # Add end date if available
                if hasattr(issue.fields, self.end_date_field):
                    end_date = getattr(issue.fields, self.end_date_field)
                    if end_date:
                        task_details.append(f"  End date: {end_date}")
                
                # Add time tracking info if available
                if hasattr(issue.fields, 'timetracking') and issue.fields.timetracking:
                    if hasattr(issue.fields.timetracking, 'originalEstimate'):
                        task_details.append(f"  Current estimate: {issue.fields.timetracking.originalEstimate}")
                
                # # Get sprint info
                # if hasattr(issue.fields, 'customfield_10108') and issue.fields.customfield_10108:
                #     sprint_data = issue.fields.customfield_10108[0]
                #     if isinstance(sprint_data, str):
                #         sprint_match = re.search(r'endDate=([^,]+)', sprint_data)
                #         if sprint_match:
                #             sprint_end = sprint_match.group(1).split('T')[0]
                #             task_details.append(f"  Sprint end date: {sprint_end}")
                #     else:
                #         if hasattr(sprint_data, 'endDate'):
                #             sprint_end = sprint_data.endDate.split('T')[0]
                #             task_details.append(f"  Sprint end date: {sprint_end}")
                
                tasks_info.append("\n".join(task_details))

            tasks_info_str = "\n\n".join(tasks_info)
            
            # Get today's date
            today_str = datetime.now().strftime('%Y-%m-%d')

            # Get sprint end date for the prompt
            sprint_end_date = None
            if issues and hasattr(issues[0].fields, 'customfield_10108') and issues[0].fields.customfield_10108:
                sprint_data = issues[0].fields.customfield_10108[0]
                if isinstance(sprint_data, str):
                    sprint_match = re.search(r'endDate=([^,]+)', sprint_data)
                    if sprint_match:
                        sprint_end_date = sprint_match.group(1).split('T')[0]
                elif hasattr(sprint_data, 'endDate'):
                    sprint_end_date = sprint_data.endDate.split('T')[0]

            prompt = f"""Analyze these Jira tasks and suggest values for missing fields.
            
            Today's date: {today_str}
            Project: {project_code}
            Sprint start date: {sprint_start_date if sprint_start_date else 'Not available'}
            Sprint end date: {sprint_end_date if sprint_end_date else 'Not available'}
            
            Available Team Members (with their roles):
            {user_info_str}
            
            Tasks Needing Updates:
            {tasks_info_str}
            
            Required Fields Explanation:
            1. End date ({self.end_date_field}): The expected completion date for the task. Estimate based on all the information provided as an experienced project manager. Remember to consider workload, priority, possible dependencies, estimated time, etc.
            2. Start date ({self.start_date_field}): When work should begin on the task. Usually the sprint start date for new tasks.
            3. assignee: The team member responsible for completing the task.
            4. Original Estimate (timetracking): The estimated hours needed to complete the task.
            
            For each task, provide:
            1. End date (YYYY-MM-DD format, must be between start date and sprint end date)
            2. assignee (use Jira username from team members list, assign based on their roles/expertise)
            3. Original Estimate (in hours, format: "Xh" where X is the number of hours)
            
            Important:
            - Front-end tasks should be assigned to front-end developers
            - Back-end tasks should be assigned to back-end developers
            - AI/ML tasks should be assigned to AI engineers
            - End dates must not exceed sprint end date ({sprint_end_date})
            - Each team members has min 4 hours/day to work on tasks
            
            Return a JSON array of objects with format:
            {{
                "key": "XXX-123",
                "updates": {{
                    "{self.end_date_field}": "YYYY-MM-DD",  # End date field
                    "{self.start_date_field}": "YYYY-MM-DD",  # Start date field
                    "assignee": "jira.username",
                    "timeoriginalestimate": "4h"
                }},
                "reasoning": {{
                    "assignee_choice": "Explanation of why this assignee was chosen...",
                    "time_estimate": "Explanation of how the time was estimated based on description and complexity...",
                    "date_planning": "Explanation of why these dates were chosen considering priority and workload..."
                }}
            }}
            
            Only include fields that were missing for each task. The field IDs map to:
            - {self.end_date_field} = End date
            - {self.start_date_field} = Start date
            - timeoriginalestimate = Original Estimate (in hours)
            
            Please provide detailed reasoning for each decision in the 'reasoning' field, but note that this field is for explanation only and won't be used in the actual Jira updates."""
            
            print(f"Prompt: {prompt}")
            max_retries = 3
            updates = None
            
            for attempt in range(max_retries):
                try:
                    print(f"\nAI Attempt {attempt + 1}/{max_retries}")
                    completion = self.client.chat.completions.create(  # Changed from ai_client to client
                        model="google/gemini-flash-1.5",
                        messages=[{"role": "user", "content": prompt}],
                        extra_headers=self.extra_headers  # Added from AIValidator
                    )
                    
                    response = completion.choices[0].message.content
                    print(f"Raw AI response: {response}")
                    
                    # Clean up response
                    cleaned_response = response.replace('```json', '').replace('```', '').strip()
                    updates = json.loads(cleaned_response)
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    print(f"Error in AI attempt {attempt + 1}: {e}")
                    if attempt == max_retries - 1:
                        print("Failed to get valid AI suggestions after all attempts")
                        return {'error': 'Failed to get AI suggestions', 'updated': 0, 'tasks': []}
            
            # Step 4: Apply updates
            print("\nStep 4: Applying updates...")
            updated_tasks = []
            
            for update in updates:
                try:
                    issue = self.jira.issue(update['key'])
                    update_dict = {}
                    
                    # Print AI's reasoning for this task
                    if 'reasoning' in update:
                        print(f"\nAI Reasoning for {update['key']}:")
                        for aspect, explanation in update['reasoning'].items():
                            print(f"  {aspect.replace('_', ' ').title()}: {explanation}")
                        print()  # Add blank line for readability
                    
                    for task in tasks_needing_update:
                        if task['key'] == update['key']:
                            # Start date
                            if 'Start date' in task['missing_fields'] and sprint_start_date:
                                update_dict[self.start_date_field] = sprint_start_date
                            
                            # End date
                            if 'End date' in task['missing_fields']:
                                end_date = update['updates'].get(self.end_date_field)
                                if end_date:
                                    update_dict[self.end_date_field] = end_date
                            
                            # Assignee
                            if 'assignee' in task['missing_fields']:
                                update_dict['assignee'] = {'name': update['updates'].get('assignee')}
                            
                            # Original Estimate
                            if 'Original Estimate' in task['missing_fields']:
                                estimate = update['updates'].get('timeoriginalestimate')
                                if estimate and isinstance(estimate, str) and estimate.endswith('h'):
                                    update_dict['timetracking'] = {
                                        'originalEstimate': estimate,
                                        'remainingEstimate': estimate
                                    }
                            break
                    
                    if update_dict:
                        print(f"Updating {update['key']} with fields: {update_dict}")
                        issue.update(fields=update_dict)
                        
                        # Convert field IDs back to readable names for the report
                        readable_fields = {
                            self.end_date_field: 'End date',
                            self.start_date_field: 'Start date',
                            'assignee': 'Assignee',
                            'timetracking': 'Original Estimate'
                        }
                        
                        # Include reasoning in the updated_tasks response
                        updated_tasks.append({
                            'key': update['key'],
                            'summary': issue.fields.summary,  # Add summary for better context
                            'updated_fields': [readable_fields.get(f, f) for f in update_dict.keys()],
                            'reasoning': update.get('reasoning', {})  # Include AI's reasoning
                        })
                        print(f"Updated {update['key']}: {update_dict}")
                        
                except Exception as e:
                    print(f"Error updating {update['key']}: {e}")
                    print(f"Response headers = {getattr(e, 'response', {}).get('headers', {})}")
                    print(f"Response text = {getattr(e, 'response', {}).get('text', '')}")
                    continue
            
            return {
                'updated': len(updated_tasks),
                'tasks': updated_tasks
            }
            
        except Exception as e:
            print(f"Error in validate_and_update_sprint_tasks: {e}")
            print(f"Full error: {traceback.format_exc()}")
            return {'error': str(e), 'updated': 0, 'tasks': []} 
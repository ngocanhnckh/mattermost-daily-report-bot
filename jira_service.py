from jira import JIRA
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from config import JIRA_URL, JIRA_TOKEN
import traceback

logger = logging.getLogger(__name__)

class JiraService:
    def __init__(self):
        """Initialize Jira service using config"""
        if not JIRA_URL or not JIRA_TOKEN:
            logger.warning("Jira credentials not configured")
            self.enabled = False
            return
            
        try:
            self.jira = JIRA(server=JIRA_URL, token_auth=JIRA_TOKEN)
            self.enabled = True
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
                if hasattr(issue.fields, 'duedate') and issue.fields.duedate:
                    end_date = datetime.strptime(issue.fields.duedate, '%Y-%m-%d')
                
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
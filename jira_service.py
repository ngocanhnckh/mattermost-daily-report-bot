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
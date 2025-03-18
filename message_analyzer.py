from ai_validator import AIValidator
from typing import List, Dict
import logging
import traceback

logger = logging.getLogger(__name__)

class MessageAnalyzer(AIValidator):
    def generate_report(self, 
                       username: str, 
                       messages: List[str], 
                       active_tasks: List[Dict],
                       recent_updates: List[Dict]) -> str:
        """Generate a daily report based on user's messages and Jira activity."""
        if not self.enabled or not self.client:
            return None
            
        try:
            # Format active tasks context
            active_tasks_context = "\n".join([
                f"- {task['key']}: {task['summary']} ({task['status']})"
                for task in active_tasks
            ])
            
            # Format recent Jira updates
            updates_context = ""
            if recent_updates:
                updates_list = []
                for update in recent_updates:
                    changes = []
                    for change in update['changes']:
                        if change['field'] == 'status':
                            changes.append(
                                f"Status changed from '{change['from']}' to '{change['to']}'"
                            )
                        elif change['field'] == 'comment':
                            changes.append("Added comment")
                    
                    if changes:
                        updates_list.append(
                            f"- {update['key']}: {update['summary']}\n  "
                            f"{chr(10).join('  ' + change for change in changes)}"
                        )
                
                if updates_list:
                    updates_context = "Recent Jira Updates:\n" + "\n".join(updates_list)
            
            # Format messages context
            messages_context = "\n".join(messages) if messages else "No messages found"
            
            prompt = f"""Generate a daily report for user {username} based on their recent activities.
            
            Active Jira Tasks:
            {active_tasks_context}
            
            {updates_context}
            
            Recent Messages:
            {messages_context}
            
            Generate a professional daily report following this format:
            1. What was accomplished yesterday (use Jira updates if available)
            2. What is planned for today (use active tasks)
            3. Any blockers or challenges
            
            Keep it concise and professional. If there's not enough information from messages,
            use the Jira updates to infer what the user has been working on."""
            
            completion = self.client.chat.completions.create(
                model="google/gemini-flash-1.5",
                extra_headers=self.extra_headers,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return completion.choices[0].message.content
            
        except Exception as e:
            print(f"Error generating AI report: {e}")
            print(f"Full error: {traceback.format_exc()}")
            return None 
from ai_validator import AIValidator
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

class MessageAnalyzer(AIValidator):
    def generate_report(self, 
                       username: str, 
                       messages: List[str], 
                       tasks: List[Dict]) -> str:
        """Generate a daily report based on user's messages and tasks"""
        if not self.enabled or not self.client:
            return None
            
        try:
            # Format tasks for context
            tasks_context = "\n".join([
                f"- {task['key']}: {task['summary']} ({task['status']})"
                for task in tasks
            ])
            
            # Format messages
            messages_context = "\n".join(messages)
            
            prompt = f"""Generate a daily report for user with username \"{username}\" based on their recent messages and active tasks.
            
            Active Jira Tasks:
            {tasks_context}
            
            Recent Messages:
            {messages_context}
            
            Generate a professional daily report following this format:
            1. What was accomplished yesterday
            2. What is planned for today
            3. Any blockers or challenges
            
            Keep it concise and professional. If there's not enough information, mention "No detailed information available"."""
            
            completion = self.client.chat.completions.create(
                model="google/gemini-flash-1.5",
                extra_headers=self.extra_headers,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return completion.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generating AI report: {e}")
            return None 
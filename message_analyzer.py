from ai_validator import AIValidator
from typing import List, Dict
import logging
import traceback
import datetime
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
            
            currentDate = datetime.datetime.now().strftime("%Y-%m-%d")
            
            prompt = f"""Generate a daily report for user {username} based on their recent activities.
            Today's date: {currentDate}
            
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

    def summarize_channel_messages(self, messages: list, username: str, user_info: dict) -> str:
        """
        Summarize all messages in the channel for yesterday and today, prioritizing those relevant to the user.
        """
        if not self.enabled or not self.client:
            return None
        try:
            # Compose a prompt for the AI
            prompt = (
                f"You are an assistant for a project team. Summarize the following channel messages from yesterday and today, "
                f"prioritizing anything that may involve or require the attention of user '{username}'. Even if message doesn't specificly mention user but it's important for the whole team to know, summarize the situation as well"
                f"User info: {user_info}. Tag the user if needed.\n"
                f"Messages:\n"
            )
            for msg in messages:
                prompt += f"- [{msg.get('timestamp', '')}] {msg.get('sender', '')}: {msg.get('text', '')}\n"
            prompt += (
                "\nReturn a concise summary, highlight action items, and mention anything that needs the user's attention."
            )
            completion = self.client.chat.completions.create(
                model="google/gemini-flash-1.5",
                extra_headers=self.extra_headers,
                messages=[{"role": "user", "content": prompt}]
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Error summarizing channel messages: {e}")
            print(f"Full error: {traceback.format_exc()}")
            return None

    def suggest_next_tasks(self, jira_tasks: list, summarized_messages: str, username: str) -> str:
        """
        Suggest what the user should do next based on their Jira tasks and recent channel activity.
        """
        if not self.enabled or not self.client:
            return None
        try:
            prompt = (
                f"You are an assistant for a project team. Here is a summary of recent channel messages for '{username}':\n"
                f"Today's date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n"
                f"{summarized_messages}\n\n"
                f"And here are all Jira tasks assigned to '{username}':\n"
            )
            for task in jira_tasks:
                prompt += f"- {task.get('key', '')}: {task.get('summary', '')} ({task.get('status', '')}) with deadline ({task.get('end_date', '')})\n"
            prompt += (
                "\nBased on the above, craft a concise report for user on what happened across all channels, what does it means to them, and what should they do next. Give your strategic opinion as well to help user facilate decision making. Also give them advise on the tasks that they should take on today based on importance and urgency matrix, tasks that overdue or in high risk that they might need to pay attention. "
                "\n The report will be divided in to 3 sections:"
                "\n 1. Summary on recent discussions"
                "\n 2. Summary on user's active task (remember to specify deadline if has, task summary, task status)"
                "\n 3. Strategic next steps they should do today (give real world example that exist in the history if have that could help them make decision)"
                "\n The report title should be something like Daily News {enter date} for {username}"
                "\n At the beginning of the report, you should greet user, wish them a good day and give them a random qoute to motivate their work, and if it fit the context of recent discussions that might help solve their problem, even better (translate to the language of the report if the qoute is in foreigner language)"
                "Prioritize urgent or blocked tasks, and mention any follow-ups from the messages. \n Give the report in multilanguage (Vietnamese and English). Use Vietnamese first, and at the top of the Vietnamese report title add (English version below)"
            )

            print(prompt)

            completion = self.client.chat.completions.create(
                model="google/gemini-flash-1.5",
                extra_headers=self.extra_headers,
                messages=[{"role": "user", "content": prompt}]
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Error suggesting next tasks: {e}")
            print(f"Full error: {traceback.format_exc()}")
            return None
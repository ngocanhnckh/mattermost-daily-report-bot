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
                f"prioritizing anything that may involve or require the attention of user '{username}'. Even if message doesn't specificly mention user but it's important for the whole team to know, summarize the situation as well. Retain the information like links (URL) if any"
                f"User info: {user_info}. Tag the user if needed.\n"
                f"Messages:\n"
            )
            for msg in messages:
                prompt += f"- [{msg.get('timestamp', '')}] {msg.get('sender', '')}: {msg.get('text', '')}\n"
            prompt += (
                "\nReturn a concise summary, highlight action items, and mention anything that needs the user's attention. Also in your summary, you must indicates what is the one final latest most recent messages (about 1-5 messages that related to eachother and were sent later in the end) is about"
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

    def define_if_need_channel_context(self, user_mesg):
        """
        Suggest if the user's message requires the agent to summarize all the recent channel messages
        """
        if not self.enabled or not self.client:
            return None
        try:
            prompt = (
                f"You are an assistant for a project team. Here is a summary of recent channel messages:\n"
                f"Today's date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n"
                f"User message: {user_mesg}\n\n"
                f"Based on the above, suggest if the user's message requires the agent to summarize all the recent channel messages."
                f"Example:\n"
                f"* User message: 'Gần đây mọi người đang nói về vấn đề gì nhỉ?' 'Dạo này có gì xảy ra không, tóm tắt cho tôi' 'Tôi có bỏ lỡ gì gần đây không' -> true\n"
                f"* User message: 'Ok, em tạo công việc đi' -> false\n"
                f"Return only 'true' or 'false' without any qoutes or special characters"
            )
            completion = self.client.chat.completions.create(
                model="google/gemini-flash-1.5",
                extra_headers=self.extra_headers,
                messages=[{"role": "user", "content": prompt}]
            )
            print(f"AI response: {completion.choices[0].message.content}")
            return completion.choices[0].message.content.strip().lower() == "true"
        except Exception as e:
            print(f"Error defining if need channel context: {e}")
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
                "\nBased on the above, send a personalized message to user (use Vietnamese). First, look for any overdue or close to deadline task and ask them about those tasks (please write out the task name, not onl the task key), ask if they have any problem with these tasks, any blockers or help needed. You can also suggest them some tasks you can create for them or other people to come in and help them with the task"
                "\n Next you concisely summary what happened in recent discussions (inclue URL if has), and give them a strategic actionable next steps they should do today to resolve situation that arised in recent discussion only if that might directly relate to them and need their action."
                
                "\n If they don't have any over due task, based on urgency and the task's importance, suggest 5 tasks that they should take on today (remember to specify deadline if has, task summary, task status)"
                "\n Write some kind words and tips / quotes to encourage them to do better, communicate more with team mates and have a productive day"
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
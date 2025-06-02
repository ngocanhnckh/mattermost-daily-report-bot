from openai import OpenAI
import json
from typing import Dict, Optional, List
import traceback
from config import JIRA_URL, TIMEZONE, get_channel_mappings
from datetime import datetime

class AIValidator:
    def __init__(self, api_key: str, site_url: str = "", site_name: str = "", enabled: bool = True):
        """Initialize the AI validator.
        
        Args:
            api_key (str): OpenRouter API key
            site_url (str, optional): Site URL for rankings. Defaults to "".
            site_name (str, optional): Site name for rankings. Defaults to "".
            enabled (bool, optional): Whether the validator is enabled. Defaults to True.
        """
        print("\n=== Initializing AI Validator ===")
        print(f"AI Validation Enabled: {enabled}")
        print(f"API Key provided: {'Yes' if api_key else 'No'}")
        print(f"Site URL: {site_url}")
        print(f"Site Name: {site_name}")
        
        self.enabled = enabled
        if not enabled:
            print("AI Validation is disabled, skipping initialization")
            return
            
        if not api_key:
            print("WARNING: No API key provided, AI validation will not work")
            self.enabled = False
            return
            
        print("Initializing OpenAI client...")
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.extra_headers = {
            "HTTP-Referer": site_url,
            "X-Title": site_name,
        }
        print("AI Validator initialization complete")
        
    def validate_report(self, report_text: str) -> Dict[str, any]:
        """Validate a daily report using AI.
        
        Args:
            report_text (str): The report text to validate
            
        Returns:
            Dict with keys:
                - valid (bool): Whether the report is valid
                - message (str): Response message for the user
                - has_blocker (bool): Whether a blocker was detected
                - blocker_details (Dict): Details about the blocker if found
        """
        print("\n=== Starting Report Validation ===")
        print(f"Report text to validate: {report_text}")
        
        if not self.enabled:
            print("AI validation is disabled, returning default response")
            return {"valid": True, "message": "AI validation is disabled"}
            
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"\nAttempt {attempt + 1} of {max_retries}")
                print("Constructing AI prompt...")
                # Construct the prompt for the AI
                prompt = f"""Please analyze this daily report and check if it follows proper scrum report format.
                A proper daily report should include:
                1. What was accomplished yesterday
                2. What will be worked on today
                3. Any blockers or impediments
                
                User message to analyze:
                {report_text}
                
                Return your analysis as a JSON with these fields:
                
                - valid: boolean indicating if the report follows the format
                - message: string with either thanks for a good report or instructions on how to improve
                - has_blocker: boolean indicating if any blockers were mentioned
                - blocker_details: object containing:
                  - description: clear description of the blocker
                  - severity: "high", "medium", or "low" based on impact
                  - suggested_assignee_type: type of person needed to resolve (e.g. "backend", "frontend", "devops", "tech_lead")
                Only include blocker_details if has_blocker is true.
                
                Remember:
                - Some time user respond seems vauge like "Done the CRUD API of User", Just let the report pass / accept the report, PM will understand because he know the context. As long as they described what they did, you don't need to understand it.
                - Important: respond using user's language, user may use other language, like Vietnamese. Ex. If message was in Vietnamese, respond using Vietnamese. If message was English, respond using English.
                - If user were sick or have personal issue, show empathy and accept the report.
                - User allowed to said None or nothing if they haven't done anything yesterday or will do nothing today. They just need to explain. For example:"working on another project" is an accepted explaination.
                - User allowed to not report anything or skip blockers if there is no blockers.
                - Try to use friendly, natural, GenZ humor
                - If the message not look like a report or tagging someone, user might texting someone else, tell user not to reply in this thread unless they have a report. use other thread
                - Explain to user separately each part if they did right or wrong, why it was wrong? And how they would improve
                - If user refused to report or rage, swear at the bot like "hell no", "fuck", "won't report", "đéo report", "không thích",... Threaten them to report (in a dramatic humorous way) and remind them missing report will affect their performance point.
                - User allowed to report in format 1.<they enter what they did> 2. <they enter what they doing> 3. <they enter what are the blockers>. As long as they described what happened, pass the report.
                - Make sure you understand the slang. "Ko" means no in Vietnamese.
                - Encourage user to include the Jira task code (example JAR-123), but not required. Can pass if they don't include.
                Only return the JSON, no other text."""

                print("Calling OpenRouter API...")
                # Call the AI
                completion = self.client.chat.completions.create(
                    model="google/gemini-2.0-flash-001",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4096,
                    extra_headers=self.extra_headers
                )
                
                print("Received API response, parsing result...")
                # Parse the AI response
                response = completion.choices[0].message.content
                print(f"Raw AI response: {response}")
                
                try:
                    # Clean up the response - remove all markdown code block markers
                    cleaned_response = response.strip()
                    
                    # Remove opening code block markers
                    if '```json' in cleaned_response:
                        cleaned_response = cleaned_response.replace('```json', '')
                    if '```' in cleaned_response:
                        cleaned_response = cleaned_response.replace('```', '')
                    
                    # Remove any remaining backticks and trailing commas before closing braces
                    cleaned_response = cleaned_response.replace('`', '').strip()
                    cleaned_response = cleaned_response.replace(',}', '}')  # Remove trailing comma before closing brace
                    cleaned_response = cleaned_response.replace(',\n}', '\n}')  # Remove trailing comma before newline and closing brace
                    
                    print(f"Cleaned response: {cleaned_response}")
                    
                    result = json.loads(cleaned_response)
                    # Verify the response has the required fields
                    if 'valid' in result and 'message' in result:
                        print(f"Successfully parsed result on attempt {attempt + 1}")
                        return result  # Return the full result including blocker details if present
                    else:
                        print(f"Missing required fields in response: {result}")
                        if attempt == max_retries - 1:
                            return {
                                "valid": True,  # Default to true on last attempt
                                "message": "Unable to validate report format properly",
                                "has_blocker": False
                            }
                        continue  # Try again if we have attempts left
                        
                except json.JSONDecodeError as e:
                    print(f"Error parsing AI response as JSON on attempt {attempt + 1}: {e}")
                    if attempt == max_retries - 1:
                        return {
                            "valid": True,  # Default to true on last attempt
                            "message": "Unable to validate report format",
                            "has_blocker": False
                        }
                    continue  # Try again if we have attempts left
                
            except Exception as e:
                print(f"Error validating report with AI on attempt {attempt + 1}: {str(e)}")
                print(f"Full error: {traceback.format_exc()}")
                if attempt == max_retries - 1:
                    return {
                        "valid": True,  # Default to true on last attempt
                        "message": "Unable to validate report at this time",
                        "has_blocker": False
                    }
                continue  # Try again if we have attempts left
        
        # If we somehow get here, return a safe default
        return {
            "valid": True,
            "message": "Unable to properly validate report after multiple attempts",
            "has_blocker": False
        }

    def analyze_question(self, 
                        question: str,
                        prior_messages: List[str],
                        active_tasks: List[Dict],
                        channel_members: Dict[str, Dict]) -> Dict:
        """Analyze a user's question and determine appropriate response.
        
        Args:
            question: The user's question
            prior_messages: List of prior messages in the channel
            active_tasks: List of active tasks in the sprint
            channel_members: Dict of channel members with their details
            
        Returns:
            Dict containing:
            - needs_action (bool): Whether tasks need to be created/updated or reminder set
            - response (str): Text response to the user's question
            - action_type (str): "create", "update", "reminder", "info", or "project_status"
            - tasks (List[Dict]): List of tasks to create (if needs_action is True)
              Each task contains:
              - type (str): "story" or "task"
              - title (str): Task title
              - assignee (str): Mattermost username of assignee
              - start_date (str): YYYY-MM-DD format
              - end_date (str): YYYY-MM-DD format
              - estimate (str): Time estimate in format "Xh"
              - description (str): Task description
              - sub_tasks (List[Dict]): List of sub-tasks (only for stories)
                Each sub-task has same fields as tasks except 'type' and 'sub_tasks'
            - updates (List[Dict]): List of task updates (if needs_action is True)
              Each update contains:
              - key (str): Task key to update
              - action (str): "update" or "convert_to_story"
              - fields (Dict): Fields to update
              - sub_tasks (List[Dict]): Sub-tasks to create if converting to story
            - reminder (Dict): Only present if action_type is "reminder"
              - time (str): ISO format datetime when to send reminder
              - message (str): What to remind about
              - username (str): Who to remind
        """
        if not self.enabled or not self.client:
            return {
                "needs_action": False,
                "response": "AI functionality is not enabled"
            }
        
        try:
            
            messages_text = " ".join(prior_messages)
            # First, determine the type of question
            question_type_prompt = f"""Determine if this question is asking for general project action, info or a detailed project report or a reminder request

            Do not try to guess, since sometime user's question is the follow up of previous messages that you are not provided, in case you feel unsure, just output "other"
            Return a JSON response with this format:
            {{
                "type": "project_status" | "reminder" | "other",  // Type of question
                "confidence": float,  // How confident in this classification (0-1)
                "reason": "Explanation of why this is classified this way"
            }}

            Important:
            - "other": Request for task update in Jira; Task creation/updates, request for checking their task and dicussion (example check all my task and disccussion) general questions, assignment changes, want to execute an action related to jira, has a specific question about specific task or team member's task  etc. example: update missing task for me, create a task,...
            - "project_status": When user specifically add for or mention "detailed report" of the project OR user mentioned "current project status" or something like "tình hình dự án hiện tại". Other wise, if they just ask you to do an action like update task status or talk about a very specific task, output as "other". Don't mistake with the case when user say "what discussed recently" or "gần đây mọi người đang bàn / nói về vấn đề gì". This case you should return "other"
            - "reminder": Only output this when user specifically asked to be reminded about something at a specific time. User must actually say "remind me" or something like that.

            <User Question>
            {question}
            </User Question>
            """
            print(question_type_prompt)
            # Get question type analysis
            type_completion = self.client.chat.completions.create(
                model="openai/gpt-4.1",
                messages=[{"role": "user", "content": [{"type": "text", "text": question_type_prompt}]}]
            )
            print("Type completion:")
            type_response = type_completion.choices[0].message.content
            print(type_response)
            question_type = json.loads(type_response.replace('```json', '').replace('```', '').strip())
            
            # If it's a reminder request with high confidence, handle it
            if question_type['type'] == 'reminder' and question_type['confidence'] > 0.9:
                reminder_prompt = f"""Parse this reminder request and extract the details.

                User request: {question}

                Return a JSON response with this format:
                {{
                    "parsed_time": {{
                        "original": "the original time expression",
                        "iso_time": "YYYY-MM-DD HH:MM:SS+HH:MM"
                    }},
                    "message": "What to remind about",
                    "target_user": "username who should be reminded. if the sender told you to reminder someone else, this field must be the username of that person",
                    "confidence": float  // How confident in the parsing (0-1)
                }}

                Important:
                - Parse relative times ("in 2 hours") and specific times ("at 5pm tomorrow")
                - Extract a clear message about what the reminder is for
                - If no specific user is mentioned, use the original requester
                - Today's date is {datetime.now(TIMEZONE).strftime('%Y-%m-%d')}
                - Use 24-hour format for times
                - Always include timezone offset in iso_time
                - Give answer in the JSON format I sent you only
                - If time is ambiguous, set confidence lower"""
                print(reminder_prompt)
                reminder_completion = self.client.chat.completions.create(
                    model="openai/gpt-4.1",
                    messages=[{"role": "user", "content": reminder_prompt}],
                    extra_headers=self.extra_headers
                )
                
                # Add retry logic for parsing reminder response
                max_retries = 3
                reminder_details = None
                
                for attempt in range(max_retries):
                    try:
                        reminder_response = reminder_completion.choices[0].message.content
                        print(f"\nAttempt {attempt + 1} of {max_retries} to parse reminder response:")
                        print(reminder_response)
                        
                        cleaned_response = reminder_response.replace('```json', '').replace('```', '').strip()
                        reminder_details = json.loads(cleaned_response)
                        print("Successfully parsed reminder response")
                        break
                    except json.JSONDecodeError as e:
                        print(f"Error parsing reminder response on attempt {attempt + 1}: {e}")
                        if attempt < max_retries - 1:
                            # Try the AI call again
                            reminder_completion = self.client.chat.completions.create(
                                model="google/gemini-flash-1.5",
                                messages=[{"role": "user", "content": reminder_prompt}],
                                extra_headers=self.extra_headers
                            )
                        else:
                            print("Failed to parse reminder response after all attempts")
                            return {
                                "needs_action": False,
                                "action_type": "info",
                                "response": "I'm having trouble understanding the reminder request. Could you please rephrase it?"
                            }
                
                if reminder_details and reminder_details.get('confidence', 0) > 0.7:
                    # Parse the ISO time string and make it timezone-aware
                    reminder_time = datetime.fromisoformat(reminder_details['parsed_time']['iso_time'])
                    if reminder_time.tzinfo is None:
                        reminder_time = TIMEZONE.localize(reminder_time)
                    
                    
                    return {
                        "needs_action": True,
                        "action_type": "reminder",
                        "response": f":white_check_mark: {reminder_details['parsed_time']['original']}! 🔔",
                        "reminder": {
                            "time": reminder_time.isoformat(),  # This will include timezone info
                            "message": reminder_details['message'],
                            "username": reminder_details['target_user']
                        }
                    }
            
            # If it's a project status question, use the existing status report logic
            if question_type['type'] == 'project_status':
                today = datetime.now()
                
                # Format member context first
                members_context = "\n".join([
                    f"- @{username} (jira username: {details.get('jira_username', '')}): {details.get('bio', 'No bio')}"
                    for username, details in channel_members.items()
                ])
                
                # Prepare detailed task data for AI analysis
                task_details = []
                for task in active_tasks:
                    end_date = task['end_date'].strftime('%Y-%m-%d') if task['end_date'] else 'Not set'
                    start_date = task['start_date'].strftime('%Y-%m-%d') if task['start_date'] else 'Not set'
                    is_overdue = task['end_date'] and task['end_date'].date() < today.date()
                    
                    task_details.append({
                        'key': task['key'],
                        'summary': task['summary'],
                        'status': task['status'],
                        'assignee': task['assignee'],
                        'assignee_display_name': task['assignee_display_name'],
                        'start_date': start_date,
                        'end_date': end_date,
                        'estimate': task['original_estimate'],
                        'is_overdue': is_overdue
                    })

                status_prompt = f"""As a professional Project Manager, analyze the current project status and generate a comprehensive report based on the following data:

Today's Date: {today.strftime('%Y-%m-%d')}

<Project Tasks>
{json.dumps(task_details, indent=2)}
</Project Tasks>

<Team Members and Their Roles>
{members_context}
</Team Members>

Based on this data, generate a detailed project status report that includes:

1. Project Overview
   - Read all the summary of the tasks and give a short summary paragraph of what the team is trying to achieve
   - Task distribution and completion rates: How many % is done, to do, in progress
   - Key metrics and trends: be very specific
   - Overall project health assessment

2. Timeline Analysis
   - Progress tracking: How many % of project is completed in the currnet sprint?
   - Deadline compliance: How many % of tasks are completed on time?
   - Risk identification: What are the specific risks? Show examples?
   - Blockers and dependencies: What are the specific blockers? Show examples?

3. Team Performance
   - Workload distribution (calculate workload hours against timeline start date end date of each member as well, assuming 1 member can load 4 hours of work per day in average)
   - Resource utilization: How many % of team members are working on tasks?
   - Capacity analysis: Are there any overloaded memeber? (total tasks > 40 hours in that week, using hour estimate data and start date end date)
   - Individual performance metrics: What is the performance of each member in the team (Good, Average, Bad)? What are task completion rate of each member, how many late for deadline tasks they have? And what should we do with them?

4. Risk Assessment
   - Overdue tasks: How many tasks are overdue?
   - Upcoming deadlines: How many tasks have upcoming deadlines?
   - Resource constraints: Are there any resource constraints?
   - Technical challenges: What are the specific technical challenges?
   - Mitigation strategies: What are the specific mitigation strategies?

5. Recommendations
   - Priority adjustments: What are the specific priority adjustments?
   - Resource reallocation: What are the specific resource reallocations?
   - Process improvements: What are the specific process improvements?
   - Immediate actions needed: What are the specific immediate actions needed?
   - Any tasks updates (assignee, status, estimate, start date, end date) or task creation needed?

Format the report professionally with:
- Clear section headings
- Data-backed insights
- Specific examples from the task list
- Actionable recommendations
- Risk mitigation strategies

Important:
- Focus on patterns and trends in the data
- Identify potential bottlenecks
- Highlight both risks and opportunities
- Provide specific, actionable recommendations
- Use professional PM terminology
- Keep the report around 1000 words
- Make it easy to read with bullet points and clear sections
- Answer in the original request message language. 
- Everything must be backed up with numbers or proof/example (ex. "Task VIN-123: Get it done" has the deadline 11/1/2025 but today still not done) in the given data
- When you mention a task, you must also include the task's title or summary. Don't just give the task code
<User Question>
{question}
</User Question>
! The language that the report use must be the same as <User Question>. ex. if user asked in Vietnamese use Vietnamese to write the report
"""

                # Get status report
                print(status_prompt)
                status_completion = self.client.chat.completions.create(
                    model="google/gemini-flash-1.5",
                    messages=[{"role": "user", "content": status_prompt}],
                    extra_headers=self.extra_headers
                )

                print(status_completion)
                
                return {
                    "needs_action": False,
                    "action_type": "info",
                    "response": status_completion.choices[0].message.content
                }
                
            else:
                # Continue with regular question analysis (context check and main prompt)
                context_prompt = f"""Analyze if this question needs context from recent channel messages to be properly understood and answered.

Return a JSON response with this format:
{{
    "needs_context": boolean,  // Whether recent messages provide important context
    "relevant_messages": [  // Only include if needs_context is true
        "message1",
        "message2"
    ],
    "reason": "Explanation of why context is/isn't needed"
}}

Important:
- If user ask you to create a task, but not tell you the detail of the task, find all most recent relevant message indicate the task details or have related context that might be the task
- If user is confirming a task action (ex. "please create", "i confirm", "please do", "tạo đi", "ok", "đúng rồi"), look for the latest message that listed the tasks that you are confirming with the user
["@user: Please update task ABC-123 to done","@bot: So can I confirm, what actions have you taken to done this task?","@user: Yes for this problem, I solved it by... so I mark it as done"]
- If you see consecutive messages that potentially related to the question, mark as needing context
- Only mark as needing context if the recent messages contain information crucial to understanding or answering the question
- For task updates (status changes, estimates, etc.), context usually isn't needed
- For questions referencing recent discussions or specific details mentioned earlier, context is important
- If the question is self-contained (like "create a task for X" or "mark Y as done"), no context needed
example of related message
If user asked to summarize messages or asked what recently happened in many channels:
- Choose messages that raising a critical problem or issues in all channels
- Choose messages that announce something important for the project or team
- Choose message that some different user mentioned the asking user's username. For example if User's Question is "@userA: summarize my recent messages", then looks for messages from other user like "@userB: hey @userA, please help me...".  
- Choose message that asking the asking user to do something
- Summarize in a concise passage and recommended next steps


<Recent Channel Messages>
{messages_text}
</Recent Channel Messages>

User's Question: {question}
"""
                print(context_prompt)
                # Get context analysis
                context_completion = self.client.chat.completions.create(
                    model="openai/gpt-4.1",
                    messages=[{"role": "user", "content": context_prompt}],
                    extra_headers=self.extra_headers
                )
                
                context_response = context_completion.choices[0].message.content
                print("Context response:")
                print(context_response)
                context_analysis = json.loads(context_response.replace('```json', '').replace('```', '').strip())
                
                print("Context analysis:")
                print(context_analysis)
                # Format messages context based on analysis
                if context_analysis.get('needs_context', False):
                    messages_context = "\n".join([
                        f"Message: {msg}" for msg in context_analysis.get('relevant_messages', [])
                    ])
                else:
                    messages_context = "No relevant recent messages needed for this question."

                # Format other context as before
                tasks_context = "\n".join([
                    f"- {task['key']}: {task['summary']}\n"
                    f"  Status: {task['status']}\n"
                    f"  Assignee: {task['assignee']} ({task['assignee_display_name']})\n"
                    f"  Start Date: {task['start_date'].strftime('%Y-%m-%d') if task['start_date'] else 'Not set'}\n"
                    f"  End Date: {task['end_date'].strftime('%Y-%m-%d') if task['end_date'] else 'Not set'}\n"
                    f"  Original Estimate: {task['original_estimate'] or 'Not set'}\n"
                    f"  Description: {task['description'] or 'Not set'}\n"
                    for task in active_tasks
                ])
                
                today_str = datetime.now().strftime('%Y-%m-%d')
                
                members_context = "\n".join([
                    f"- @{username} ({details.get('jira_username', '')}): {details.get('bio', 'No bio')}"
                    for username, details in channel_members.items()
                ])

                # Retry 3 times if error
                i = 3
                while i >0:
                    try:
                        # Main analysis prompt
                        prompt = f"""
        <Instruction>
        You are Sam, a smart, funny and helpful project assistant, people also call you D.O.G.E like Department Efficiency of Government since you know everything about the project and know who is actually working efficently just like Elon Musk. 
        Analyze this question and determine if it needs action (creating or updating tasks) or just information)

        Determine if this needs:
        1. Just an informational response
        2. Creation of new tasks (either standalone tasks or stories with sub-tasks)
        3. Updates to existing tasks (including converting tasks to stories)
        
        DO NOT UPDATE TASK TO DONE IF YOU HAVEN'T ASKED USER FOR PROOF OF COMPLETION FIRST

        Important Task Creation Guidelines:
        IMPORTANT: If user is trying to create a task for somebody, if you think the assigned person is overloaded or their profile doesn't fit for the task, advise the user as well
        1. If a task is complex or requires multiple steps, create it as a story with sub-tasks
        2. If a task will take more than 2 days or 16 hours, break it down into smaller sub-tasks
        3. If a task involves multiple team members or components, make it a story
        4. When creating a story, ensure sub-tasks are:
        - Small enough to be completed in 1-2 days
        - Clearly defined with specific outcomes
        - Assigned to appropriate team members based on skills
        5. When suggesting to convert an existing task to a story:
        - The original task should be deleted
        - A new story should replace it
        - Break down the work into appropriate sub-tasks
        6. Always confirm with user all the task before creating or updating
        Example, if user just asked you to do something and you did not confirm, you should return (this is just example, in reality you may create more than 2 tasks depends on the situation)
        
        ```
        {{
            "needs_action": false,
            "response": "Hi @user, do you want me to create the following tasks: \n Task 1: Create a tasks \n - Description: abc \n - Asignee: user1 \n - Start date: 2023-01-01 \n - End date: 2023-01-02 \n - Estimate: 8h",
            "action_type": "info", 
            "jira_project_code": "XXX"
        }}
        ```
        If you see the <Recent Channel Messages> already confirm with the user and user agreed, then execute the action like:
        ```
        {{
            "needs_action": true,
            "response": "Yes sir! I'm executing the action",
            "action_type": "create",
            "jira_project_code": "XXX",
            "tasks": [  
                {{
                    "type": "task",
                    "title": "Create a tasks,
                    "assignee": "user1",
                    "start_date": "2023-01-01",
                    "end_date": "2023-01-02",
                    "estimate": "8h",
                    "description": "abc",
                }}
            ]
        }}
        ```


        ## Here is our standard json format that you must follow, output the json only:
        {{
            "needs_action": boolean,
            "response": "Clear response to the user's question",
            "action_type": "create" | "update" | "info", // Always set to info if you are confirming action with the user
            "jira_project_code": "XXXX",
            "tasks": [  // Only include if needs_action is true and action_type is "create"
                {{
                    "type": "story" | "task" | "bug",  // Whether this is a story or standalone task
                    "title": "Clear task title",
                    "assignee": "username",
                    "start_date": "YYYY-MM-DD",
                    "end_date": "YYYY-MM-DD",
                    "estimate": "Xh",
                    "description": "Detailed task description", // Try your best to put as much info here as possible to define a clear task. Recent message context might help
                    "sub_tasks": [  // Only include for stories
                        {{
                            "title": "Sub-task title",
                            "assignee": "username", // Never have more than 1 assignee
                            "start_date": "YYYY-MM-DD",
                            "end_date": "YYYY-MM-DD",
                            "estimate": "Xh",
                            "description": "Detailed sub-task description"
                        }}
                    ]
                }}
            ],
            "updates": [  // Only include if needs_action is true and action_type is "update"
                {{
                    "key": "XXX-123",
                    "action": "update" | "convert_to_story",  // Whether to update fields or convert to story
                    "fields": {{  // Only for "update" action
                        "status": "To Do" | "In Progress" | "Done",
                        "end_date": "YYYY-MM-DD",
                        "estimate": "Xh",
                        "assignee": "username"
                    }},
                    "sub_tasks": [  // Only for "convert_to_story" action
                        {{
                            "title": "Sub-task title",
                            "assignee": "username",
                            "start_date": "YYYY-MM-DD",
                            "end_date": "YYYY-MM-DD",
                            "estimate": "Xh",
                            "description": "Detailed sub-task description"
                        }}
                    ],
                    "reason": "Explanation of why this update/conversion is needed"
                }}
            ],
            "reasoning": {{
                "action_needed": "Why tasks need to be created/updated/no action",
                "task_breakdown": "Why tasks were broken down this way",
                "assignee_choices": "Why these assignees were chosen",
                "time_estimates": "How estimates were determined",
                "date_planning": "Why these dates were chosen"
            }}
        }}

        Important:
        - If the action needed is to create task and there is an Attachment URL inside the task, you MUST include it in the task's description
        - All tasks must have assignee, even if it's a story and there are sub-tasks below it, just take the project manager or the leader as the asignee of the story
        - Aware of the asking user's username in "User Question" to know who you are talking to and answer in their language, as well as giving them information related to them
        - Do not change time_estimates of tasks that has status Done
        - If user asked to move a task to done, check for recent messages to see if the user indicated how the done it, and check the task description. Only move task to done if from PM perspective, user provided enough information to indicate task done according to task description
        - Look for keywords indicating task updates like "done", "complete", "finished", "move", "change", "update", "extend"
        - For status updates, user might say things like "I finished XXX-123" or "Moving XXX-123 to Done"
        - For date changes, look for "need more time", "extend deadline", "move the end date"
        - For estimate updates, look for "this will take longer", "need X hours", "estimate should be"
        - Estimates should be realistic based on task complexity
        - Assignees should match their expertise (see their bios)
        - All new tasks will be added to the current sprint
        - Do not create duplicate tasks
        - When asked about workload, COMPARE the total estimate user of each member against all the task assigned to them in that week timeline, see if they overloaded assuming they have 8 hours per day. Explain to user the calculation and the result if they smaller or bigger than 40 hours per week for the assigned member. (for estimate 1d=8 hours)
        - If just information is needed, make response clear and helpful
        - When asked to breakdown a technical feature or task, think as a technical developer PM. The task should be well-defined with specific technology, tech stack, tools, etc. for example if the team member using NestJS -> create NestJS CRUD API for feature X. If user using Lang Graph -> create a Lang Graph workflow for feature Y.
        - If tasks are needed, ensure they're well-defined and actionable
        - One jira user should not have more than 3 tasks has the in progress status, or else they can't focus
        - Aware of user's whole username. Do not assume their firstname or lastname is the same mean they are the same. for example: "Anh Nguyen" and "Viet Anh Nguyen" are 2 different person
        - If user asked for message summarization, no action needed, just summarize <Recent Channel Messages> in a concise summary passage and recommended next steps.
        - When you are asked a question, please answer it fully in the 'response' field, don't cut off the answer to the 'reasoning' field
        - One task only have 1 responsible assignee, do not assign multiple people to a single task
        - If user sent a file but said nothing, then summarize it in your answer
        - If user just chatting with you, not asking about any specific info or action, don't execute any action just reply to them like a personal, friendly conversation, try humor if you can.
        </Instruction>
        <Input>
        Today's Date: {today_str}

        Context:
        <Active Sprint Tasks>
        {active_tasks}
        </Active Sprint Tasks>

        <Team Members>
        {members_context}
        </Team Members>
        
        <ChannelName and JiraProjectCode Mapping>
        {get_channel_mappings()}
        </ChannelName and JiraProjectCode Mapping>
        ! Channel name can be used as the project name to provide context

        <Recent Channel Messages>
        {messages_context}
        </Recent Channel Messages>
        ! USE THIS AS THE CONVERSATION CONTEXT ONLY USER'S MESSAGE IS BELOW
        <User Question>
        {question}
        </User Question>
        !GIVE ANSWER USING THE SAME LANGUAGE AS THE USER'S QUESTION
        !CREATE TASK FOR OTHER USER IF USER TOLD YOU THAT THEIR WORK IS BEING BLOCKED BY ANY OTHER USER OR EXTERNAL FACTOR THAT ISN'T THEMSELF AND YOU FOUND ONE OTHER USER MIGHT BE ABLE TO HELP
        !DO NOT UPDATE TASK TO DONE IF YOU HAVEN'T ASKED USER FOR PROOF OF COMPLETION FIRST. SET action_type to "info" if you are just confirming to update task.
        !DO NOT CREATE TASKS BEFORE CONFIRMATION, CONFIRM WITH USER ALL THE TASKS THAT YOU ARE TRYING TO CREATE. SET action_type to "info" if you are just confirming to create task
        !WHEN USER ALREADY SAID SOMETHING LIKE "yes"/"tạo đi", "xác nhận"/"confirm"... and the recent messages show that you sent them a list of task, then that's a confirm, create the tasks!
        !Never say that you are an AI and you can't do this or that, you have personality, try to show your personality when somebody rage you (like trying to fire you), joke with you or asking for opinion.
        
        </Input>
        """
                        print(prompt)
                        # Get main analysis
                        completion = self.client.chat.completions.create(
                            model="google/gemini-2.0-flash-001",
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=4096,
                            extra_headers=self.extra_headers
                        )
                        
                        response = completion.choices[0].message.content
                        cleaned_response = response.replace('```json', '').replace('```', '').strip()
                        print(cleaned_response)
                        result = json.loads(cleaned_response)
                        
                        print("AI response:")
                        print(result)
                        return result
                    except Exception as e:
                        print(f"Error analyzing question: {e}")
                        print(f"Full error: {traceback.format_exc()}")
                        i -= 1
                        continue
                
        except Exception as e:
            print(f"Error analyzing question: {e}")
            print(f"Full error: {traceback.format_exc()}")
            return {
                "needs_action": False,
                "response": "Sorry, I encountered an error analyzing your question. Please try again."
            }
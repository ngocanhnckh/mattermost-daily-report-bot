from openai import OpenAI
import json
from typing import Dict, Optional, List
import traceback
from config import JIRA_URL
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
                    model="google/gemini-flash-1.5",
                    extra_headers=self.extra_headers,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
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
            prior_messages: List of 10 prior messages in the channel
            active_tasks: List of active tasks in the sprint
            channel_members: Dict of channel members with their details
            
        Returns:
            Dict containing:
            - needs_action (bool): Whether tasks need to be created
            - response (str): Text response to the user's question
            - tasks (List[Dict]): List of tasks to create (if needs_action is True)
              Each task contains:
              - title (str): Task title
              - assignee (str): Mattermost username of assignee
              - start_date (str): YYYY-MM-DD format
              - end_date (str): YYYY-MM-DD format
              - estimate (str): Time estimate in format "Xh"
              - description (str): Task description
        """
        if not self.enabled or not self.client:
            return {
                "needs_action": False,
                "response": "AI functionality is not enabled"
            }
        
        try:
            # Format context for AI with more detailed task information
            tasks_context = "\n".join([
                f"- {task['key']}: {task['summary']}\n"
                f"  Status: {task['status']}\n"
                f"  Assignee: {task['assignee']} ({task['assignee_display_name']})\n"
                f"  Start Date: {task['start_date'].strftime('%Y-%m-%d') if task['start_date'] else 'Not set'}\n"
                f"  End Date: {task['end_date'].strftime('%Y-%m-%d') if task['end_date'] else 'Not set'}\n"
                f"  Original Estimate: {task['original_estimate'] or 'Not set'}"
                for task in active_tasks
            ])
            
            # Add today's date for context
            today_str = datetime.now().strftime('%Y-%m-%d')
            
            members_context = "\n".join([
                f"- @{username} ({details.get('jira_username', '')}): {details.get('bio', 'No bio')}"
                for username, details in channel_members.items()
            ])
            
            messages_context = "\n".join([
                f"Message: {msg}" for msg in prior_messages
            ])
            
            prompt = f"""Analyze this question and determine if it needs action (creating or updating tasks) or just information.

Today's Date: {today_str}

User Question: {question}

Context:
<Active Sprint Tasks>
{tasks_context}
</Active Sprint Tasks>

<Team Members>
{members_context}
</Team Members>

<Recent Channel Messages>
{messages_context}
</Recent Channel Messages>


Determine if this needs:
1. Just an informational response
2. Creation of new tasks
3. Updates to existing tasks
- Warning: if the Recent Channel Messages do not relate to the current question, or there are issues already resolved, ignore it.

Return a JSON response with this format:
{{
    "needs_action": boolean,
    "response": "Clear response to the user's question",
    "action_type": "create" | "update" | "info",  // Type of action needed
    "tasks": [  // Only include if needs_action is true and action_type is "create"
        {{
            "title": "Clear task title",
            "assignee": "username",
            "start_date": "YYYY-MM-DD",
            "end_date": "YYYY-MM-DD",
            "estimate": "Xh",
            "description": "Detailed task description"
        }}
    ],
    "updates": [  // Only include if needs_action is true and action_type is "update"
        {{
            "key": "XXX-123",  // The Jira task key to update
            "fields": {{
                "status": "To Do" | "In Progress" | "Done",  // Optional
                "end_date": "YYYY-MM-DD",  // Optional
                "estimate": "Xh",  // Optional
                "assignee": "username"  // Optional
            }},
            "reason": "Explanation of why this update is needed"
        }}
    ],
    "reasoning": {{
        "action_needed": "Why tasks need to be created/updated/no action",
        "assignee_choices": "Why these assignees were chosen",
        "time_estimates": "How estimates were determined",
        "date_planning": "Why these dates were chosen"
    }}
}}

Important:
- Today's date is {today_str}, all start dates must be >= today
- Look for keywords indicating task updates like "done", "complete", "finished", "move", "change", "update", "extend"
- For status updates, user might say things like "I finished XXX-123" or "Moving XXX-123 to Done"
- For date changes, look for "need more time", "extend deadline", "move the end date"
- For estimate updates, look for "this will take longer", "need X hours", "estimate should be"
- Estimates should be realistic based on task complexity
- Assignees should match their expertise (see their bios)
- Answer using user's language and style of communication
- All new tasks will be added to the current sprint
- You can create many new tasks in case user request a feature
- Do not create duplicate tasks
- If just information is needed, make response clear and helpful
- If tasks are needed, ensure they're well-defined and actionable"""

            print(prompt)

            completion = self.client.chat.completions.create(
                model="google/gemini-flash-1.5",
                messages=[{"role": "user", "content": prompt}],
                extra_headers=self.extra_headers
            )
            
            response = completion.choices[0].message.content
            
            # Clean and parse response
            cleaned_response = response.replace('```json', '').replace('```', '').strip()
            result = json.loads(cleaned_response)
            
            return result
            
        except Exception as e:
            print(f"Error analyzing question: {e}")
            print(f"Full error: {traceback.format_exc()}")
            return {
                "needs_action": False,
                "response": "Sorry, I encountered an error analyzing your question. Please try again."
            }
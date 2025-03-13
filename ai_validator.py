from openai import OpenAI
import json
from typing import Dict, Optional
import traceback

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
                
                Return your analysis as a JSON with two fields:
                
                - valid: boolean indicating if the report follows the format
                - message: string with either thanks for a good report or instructions on how to improve. If the report is valid, notice them **the report is accepted** and they don't need to reply further
                
                Remember:
                - Some time user respond seems vauge like "Done the CRUD API of User", "continue fixing the feedback bug", Just let the report pass / accept the report, PM will understand because he know the context. As long as they described what they did, you don't need to understand it.
                - If user say something like "Nothing, my work already done", let them pass the report without checking for all the parts, since all their tasks for the project already done.
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
                        return {
                            "valid": result["valid"],
                            "message": result["message"]
                        }
                    else:
                        print(f"Missing required fields in response: {result}")
                        if attempt == max_retries - 1:
                            return {
                                "valid": True,  # Default to true on last attempt
                                "message": "Unable to validate report format properly"
                            }
                        continue  # Try again if we have attempts left
                        
                except json.JSONDecodeError as e:
                    print(f"Error parsing AI response as JSON on attempt {attempt + 1}: {e}")
                    if attempt == max_retries - 1:
                        return {
                            "valid": True,  # Default to true on last attempt
                            "message": "Unable to validate report format"
                        }
                    continue  # Try again if we have attempts left
                
            except Exception as e:
                print(f"Error validating report with AI on attempt {attempt + 1}: {str(e)}")
                print(f"Full error: {traceback.format_exc()}")
                if attempt == max_retries - 1:
                    return {
                        "valid": True,  # Default to true on last attempt
                        "message": "Unable to validate report at this time"
                    }
                continue  # Try again if we have attempts left
        
        # If we somehow get here, return a safe default
        return {
            "valid": True,
            "message": "Unable to properly validate report after multiple attempts"
        } 
from twilio.rest import Client
from config import (
    TWILIO_ENABLED, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER, TWILIO_SMS_TEMPLATE
)
import logging
import traceback
import re

logger = logging.getLogger(__name__)

class TwilioService:
    def __init__(self):
        self.enabled = TWILIO_ENABLED
        if self.enabled:
            print("Twilio Enabled")
            try:
                # Log Twilio credentials (masked)
                masked_sid = TWILIO_ACCOUNT_SID[:6] + "..." + TWILIO_ACCOUNT_SID[-4:]
                masked_token = TWILIO_AUTH_TOKEN[:4] + "..." + TWILIO_AUTH_TOKEN[-4:]
                print(f"Initializing Twilio with SID: {masked_sid}, Token: {masked_token}")
                print(f"From number: {TWILIO_FROM_NUMBER}")
                
                self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                self.from_number = TWILIO_FROM_NUMBER
                
                # Validate the from_number
                try:
                    self.client.incoming_phone_numbers.list(phone_number=self.from_number)
                    print(f"From number {self.from_number} is valid")
                except Exception as e:
                    print(f"Warning: From number {self.from_number} validation failed: {e}")
                
                logger.info("Twilio service initialized successfully")
                print("Twilio service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio service: {e}")
                print(f"Failed to initialize Twilio service: {e}")
                logger.error(traceback.format_exc())
                self.enabled = False
        else:
            print("Twilio Disabled")

    def format_phone_number(self, number: str) -> str:
        """Format phone number to E.164 format."""
        # Remove any spaces or special characters
        number = re.sub(r'[^\d+]', '', number)
        
        # Ensure it starts with +
        if not number.startswith('+'):
            number = '+' + number
            
        # For Vietnamese numbers (+84)
        if number.startswith('+'):
            # Remove any leading zeros after the country code
            if len(number) > 3:  # After country code
                country_code = number[:3]  # +84
                local_number = number[3:].lstrip('0')
                # Ensure the local number starts with a valid area code
                if local_number.startswith('0'):
                    local_number = local_number[1:]
                number = country_code + local_number
                
        print(f"Formatted phone number: {number}")
        return number

    def validate_phone_number(self, number: str) -> bool:
        """Validate phone number format."""
        formatted_number = self.format_phone_number(number)
        
        # Check if it starts with + and has at least 10 digits
        if not formatted_number.startswith('+') or len(formatted_number) < 11:
            print(f"Invalid phone number format: {formatted_number}")
            return False
            
        return True
    
    def send_sms(self, to_number: str, username: str, channel_name: str, thread_link: str) -> bool:
        """
        Send an SMS reminder to a user.
        
        Args:
            to_number (str): The recipient's phone number
            username (str): The username to personalize the message
            channel_name (str): The channel name where the report is needed
            thread_link (str): The link to the report thread
            
        Returns:
            bool: True if SMS was sent successfully, False otherwise
        """
        if not self.enabled:
            logger.info("SMS notifications are disabled")
            return False
            
        try:
            # Format and validate phone number
            formatted_number = self.format_phone_number(to_number)
            if not self.validate_phone_number(formatted_number):
                logger.error(f"Invalid phone number format: {formatted_number}")
                return False
            
            # Format the message using the template
            message = TWILIO_SMS_TEMPLATE.format(
                username=username,
                channel_name=channel_name,
                thread_link=thread_link
            )
            
            print(f"\nAttempting to send SMS:")
            print(f"Original number: {to_number}")
            print(f"Formatted number: {formatted_number}")
            print(f"From: {self.from_number}")
            print(f"Message: {message}")
            
            # Send the SMS
            result = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=formatted_number
            )
            
            print(f"SMS sent successfully. Message SID: {result.sid}")
            logger.info(f"SMS sent successfully to {formatted_number} (SID: {result.sid})")
            return True
            
        except Exception as e:
            error_msg = str(e)
            print(f"\nFailed to send SMS to {formatted_number}")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {error_msg}")
            print(f"Full traceback:\n{traceback.format_exc()}")
            
            # Log specific Twilio error codes
            if hasattr(e, 'code'):
                print(f"Twilio error code: {e.code}")
            if hasattr(e, 'status'):
                print(f"HTTP status: {e.status}")
            if hasattr(e, 'uri'):
                print(f"Request URI: {e.uri}")
                
            logger.error(f"Failed to send SMS to {formatted_number}: {error_msg}")
            logger.error(traceback.format_exc())
            return False 
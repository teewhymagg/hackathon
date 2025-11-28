import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
from datetime import datetime
import logging

from config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    TARGET_EMAIL,
)
from templates import format_email_html, format_email_text

logger = logging.getLogger(__name__)


def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
) -> bool:
    """
    Send an email using SMTP.
    Returns True if successful, False otherwise.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.error("SMTP credentials not configured. Cannot send email.")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add text and HTML parts
        if text_content:
            text_part = MIMEText(text_content, 'plain', 'utf-8')
            msg.attach(text_part)
        
        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}", exc_info=True)
        return False


def send_daily_reminder_email(
    to_email: str,
    user_name: Optional[str],
    upcoming_deadlines: List[Dict],
    last_meeting_summary: Optional[Dict],
) -> bool:
    """
    Send daily reminder email with upcoming deadlines and last meeting summary.
    """
    subject = "Daily Reminder: Upcoming Deadlines & Last Meeting Summary"
    
    if not upcoming_deadlines and not last_meeting_summary:
        logger.info(f"No deadlines or meetings to report for {to_email}. Skipping email.")
        return True
    
    html_content = format_email_html(
        user_name=user_name,
        upcoming_deadlines=upcoming_deadlines,
        last_meeting_summary=last_meeting_summary,
    )
    
    text_content = format_email_text(
        user_name=user_name,
        upcoming_deadlines=upcoming_deadlines,
        last_meeting_summary=last_meeting_summary,
    )
    
    return send_email(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )


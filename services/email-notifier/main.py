import logging
import sys
import os
import argparse
import threading
from datetime import datetime, time
from typing import Optional
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel

from config import (
    EMAIL_SEND_TIME,
    EMAIL_TIMEZONE,
    TARGET_EMAIL,
    DEADLINE_DAYS_AHEAD,
    LOG_LEVEL,
)
from database import (
    SessionLocal,
    get_upcoming_deadlines,
    get_meeting_summary,
    get_all_users_with_meetings,
)
from email_service import send_daily_reminder_email

# Import models for HTTP endpoint
import sys as sys_module
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '../..')
shared_models_path = os.path.join(project_root, 'libs/shared-models')
sys_module.path.insert(0, shared_models_path)

from shared_models.models import Meeting, User

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("email_notifier")

# FastAPI app for HTTP endpoint
app = FastAPI(title="Email Notification Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EmailTriggerRequest(BaseModel):
    meeting_id: Optional[int] = None
    user_id: Optional[int] = None
    user_email: Optional[str] = None


@app.post("/trigger")
async def trigger_email_endpoint(
    request: EmailTriggerRequest,
    background_tasks: BackgroundTasks
):
    """
    HTTP endpoint to trigger email sending for a specific meeting/user.
    """
    logger.info(f"Received email trigger request: meeting_id={request.meeting_id}, user_id={request.user_id}, user_email={request.user_email}")
    
    # Run email sending in background
    background_tasks.add_task(
        send_email_for_meeting,
        meeting_id=request.meeting_id,
        user_id=request.user_id,
        user_email=request.user_email,
    )
    
    return {"status": "accepted", "message": "Email sending triggered"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


def send_email_for_meeting(
    meeting_id: Optional[int] = None,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
):
    """
    Send email for a specific meeting/user.
    Called from HTTP endpoint or directly.
    """
    session = SessionLocal()
    try:
        if meeting_id:
            # Send email for specific meeting
            meeting = session.query(Meeting).filter(Meeting.id == meeting_id).first()
            if not meeting:
                logger.warning(f"Meeting {meeting_id} not found")
                return
            
            user_id = meeting.user_id
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"User {user_id} not found for meeting {meeting_id}")
                return
            
            # Get notification email from user data if set, otherwise use user email
            notification_email = user.email
            if user.data and isinstance(user.data, dict):
                notification_email = user.data.get('notification_email', user.email)
            
            # Send email for the specific meeting that was just processed
            send_reminders_for_meeting(
                session=session,
                meeting_id=meeting_id,
                user_id=user.id,
                user_email=notification_email,
                user_name=user.name,
            )
            return
        elif user_id:
            # Send email for specific user
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"User {user_id} not found")
                return
            
            send_reminders_for_user(
                user_id=user.id,
                user_email=user.email,
                user_name=user.name,
            )
        elif user_email:
            # Send email to specific email address
            users = get_all_users_with_meetings(session)
            target_user = next((u for u in users if u['email'] == user_email), None)
            if target_user:
                send_reminders_for_user(
                    user_id=target_user['id'],
                    user_email=user_email,
                    user_name=target_user.get('name'),
                )
            else:
                logger.warning(f"User with email {user_email} not found")
        else:
            # Send to all users
            send_daily_reminders()
    except Exception as e:
        logger.error(f"Error sending email: {e}", exc_info=True)
    finally:
        session.close()


def send_reminders_for_meeting(
    session,
    meeting_id: int,
    user_id: int,
    user_email: str,
    user_name: Optional[str],
):
    """Send reminder email for a specific meeting that was just processed."""
    try:
        logger.info(f"Processing email for meeting {meeting_id}, user {user_id} ({user_email})")
        
        # Get upcoming deadlines
        deadlines = get_upcoming_deadlines(session, days_ahead=DEADLINE_DAYS_AHEAD)
        user_deadlines = [d for d in deadlines if d['user_email'] == user_email]
        
        # Get summary for THIS specific meeting
        meeting_summary = get_meeting_summary(session, meeting_id=meeting_id)
        
        # Always send email if meeting summary exists (even if no deadlines)
        if meeting_summary:
            success = send_daily_reminder_email(
                to_email=user_email,
                user_name=user_name,
                upcoming_deadlines=user_deadlines,
                last_meeting_summary=meeting_summary,
            )
            if success:
                logger.info(f"Successfully sent email for meeting {meeting_id} to {user_email}")
            else:
                logger.error(f"Failed to send email for meeting {meeting_id} to {user_email}")
        else:
            logger.warning(f"No summary found for meeting {meeting_id}. Skipping email.")
            
    except Exception as e:
        logger.error(f"Error processing email for meeting {meeting_id}: {e}", exc_info=True)


def send_reminders_for_user(user_id: int, user_email: str, user_name: Optional[str]):
    """Send reminder email for a specific user."""
    session = SessionLocal()
    try:
        logger.info(f"Processing reminders for user {user_id} ({user_email})")
        
        # Get upcoming deadlines
        deadlines = get_upcoming_deadlines(session, days_ahead=DEADLINE_DAYS_AHEAD)
        user_deadlines = [d for d in deadlines if d['user_email'] == user_email]
        
        # Get meeting summary (most recent for user)
        last_summary = get_meeting_summary(session, user_id=user_id)
        
        # Send email if there's something to report
        if user_deadlines or last_summary:
            success = send_daily_reminder_email(
                to_email=user_email,
                user_name=user_name,
                upcoming_deadlines=user_deadlines,
                last_meeting_summary=last_summary,
            )
            if success:
                logger.info(f"Successfully sent reminder email to {user_email}")
            else:
                logger.error(f"Failed to send reminder email to {user_email}")
        else:
            logger.info(f"No deadlines or meetings to report for {user_email}. Skipping email.")
            
    except Exception as e:
        logger.error(f"Error processing reminders for user {user_id}: {e}", exc_info=True)
    finally:
        session.close()


def send_daily_reminders():
    """Send daily reminder emails to all users."""
    logger.info("Starting daily reminder email job")
    
    session = SessionLocal()
    try:
        # Get all users with meetings
        users = get_all_users_with_meetings(session)
        
        if not users:
            logger.info("No users with meetings found. Skipping email job.")
            return
        
        logger.info(f"Found {len(users)} users with meetings")
        
        # If TARGET_EMAIL is set, send only to that email (for testing)
        if TARGET_EMAIL:
            logger.info(f"TARGET_EMAIL is set. Sending to {TARGET_EMAIL} only.")
            # Find user by email or use first user's data
            target_user = next((u for u in users if u['email'] == TARGET_EMAIL), users[0])
            send_reminders_for_user(
                user_id=target_user['id'],
                user_email=TARGET_EMAIL,
                user_name=target_user.get('name'),
            )
        else:
            # Send to all users
            for user in users:
                send_reminders_for_user(
                    user_id=user['id'],
                    user_email=user['email'],
                    user_name=user.get('name'),
                )
        
        logger.info("Daily reminder email job completed")
        
    except Exception as e:
        logger.error(f"Error in daily reminder email job: {e}", exc_info=True)
    finally:
        session.close()


def run_http_server():
    """Run the HTTP server for email triggers."""
    port = int(os.environ.get("EMAIL_NOTIFIER_PORT", "8003"))
    logger.info(f"Starting HTTP server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


def main():
    """Main entry point for the email notification service."""
    parser = argparse.ArgumentParser(description='Email Notification Service')
    parser.add_argument(
        '--trigger',
        action='store_true',
        help='Send emails immediately and exit (for testing)'
    )
    parser.add_argument(
        '--email',
        type=str,
        help='Send email to specific address (overrides TARGET_EMAIL env var)'
    )
    parser.add_argument(
        '--http-only',
        action='store_true',
        help='Run only HTTP server (no scheduler)'
    )
    args = parser.parse_args()
    
    # If --trigger flag is set, send emails immediately and exit
    if args.trigger:
        logger.info("Manual trigger mode: Sending emails immediately...")
        target_email = args.email or TARGET_EMAIL
        
        session = SessionLocal()
        try:
            users = get_all_users_with_meetings(session)
            
            if not users:
                logger.warning("No users with meetings found.")
                return
            
            if target_email:
                logger.info(f"Sending to specific email: {target_email}")
                target_user = next((u for u in users if u['email'] == target_email), None)
                if target_user:
                    send_reminders_for_user(
                        user_id=target_user['id'],
                        user_email=target_email,
                        user_name=target_user.get('name'),
                    )
                else:
                    logger.warning(f"User with email {target_email} not found. Sending to first user.")
                    send_reminders_for_user(
                        user_id=users[0]['id'],
                        user_email=target_email,
                        user_name=users[0].get('name'),
                    )
            else:
                logger.info("Sending to all users...")
                for user in users:
                    send_reminders_for_user(
                        user_id=user['id'],
                        user_email=user['email'],
                        user_name=user.get('name'),
                    )
        finally:
            session.close()
        
        logger.info("Manual trigger completed. Exiting.")
        return
    
    # If --http-only flag, run only HTTP server
    if args.http_only:
        run_http_server()
        return
    
    # Check if scheduler should be enabled
    enable_scheduler = os.environ.get("ENABLE_EMAIL_SCHEDULER", "false").lower() == "true"
    
    if enable_scheduler:
        # Start both scheduler and HTTP server
        logger.info("Starting Email Notification Service (scheduler + HTTP server mode)")
        
        # Start HTTP server in background thread
        http_thread = threading.Thread(target=run_http_server, daemon=True)
        http_thread.start()
        logger.info("HTTP server started in background thread")
        
        # Parse send time
        try:
            hour, minute = map(int, EMAIL_SEND_TIME.split(':'))
        except ValueError:
            logger.error(f"Invalid EMAIL_SEND_TIME format: {EMAIL_SEND_TIME}. Expected HH:MM")
            sys.exit(1)
        
        # Get timezone
        try:
            tz = pytz.timezone(EMAIL_TIMEZONE)
        except pytz.exceptions.UnknownTimeZoneError:
            logger.error(f"Unknown timezone: {EMAIL_TIMEZONE}. Using UTC.")
            tz = pytz.UTC
        
        # Create scheduler
        scheduler = BlockingScheduler(timezone=tz)
        
        # Schedule daily job
        scheduler.add_job(
            send_daily_reminders,
            trigger=CronTrigger(hour=hour, minute=minute),
            id='daily_reminders',
            name='Send daily reminder emails',
            replace_existing=True,
        )
        
        logger.info(f"Scheduled daily reminders at {EMAIL_SEND_TIME} {EMAIL_TIMEZONE}")
        
        # Start scheduler
        try:
            logger.info("Scheduler started. Waiting for scheduled jobs...")
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped")
    else:
        # HTTP-only mode (default) - emails triggered after each meeting
        logger.info("Starting Email Notification Service (HTTP-only mode - triggered after meetings)")
        run_http_server()


if __name__ == "__main__":
    main()


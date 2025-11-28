import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "hackathon_bot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# Email configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "AI Scrum Master")

# Email notification settings
EMAIL_SEND_TIME = os.getenv("EMAIL_SEND_TIME", "09:00")  # Format: HH:MM (24-hour)
EMAIL_TIMEZONE = os.getenv("EMAIL_TIMEZONE", "UTC")  # Timezone for scheduling
TARGET_EMAIL = os.getenv("TARGET_EMAIL", "")  # Default target email (can be overridden per user)

# Deadline settings
DEADLINE_DAYS_AHEAD = int(os.getenv("DEADLINE_DAYS_AHEAD", "7"))  # Show deadlines within N days

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


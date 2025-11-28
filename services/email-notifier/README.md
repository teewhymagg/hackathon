# Email Notification Service

This service sends daily reminder emails with upcoming deadlines and contextualized meeting summaries including transcriptions, insights, blockers, and key highlights.

## Features

- **Daily Scheduled Emails**: Sends emails at a configured time each morning
- **Manual Trigger**: Send emails on-demand for testing with `--trigger` flag
- **Upcoming Deadlines**: Lists all action items with deadlines within the next N days (default: 7)
- **Contextualized Meeting Summary**: Includes:
  - Full meeting summary
  - Blockers identified
  - Deadlines mentioned
  - Key speaker highlights
  - Transcript statistics
  - Meeting insights and dashboards data

## Usage

### Scheduled Mode (Default)

The service runs automatically and sends emails at the configured time:

```bash
docker-compose up email-notifier
```

### Manual Trigger Mode (Testing)

Send emails immediately on-demand:

```bash
# Send to all users
docker exec -it <container-name> python main.py --trigger

# Send to specific email
docker exec -it <container-name> python main.py --trigger --email user@example.com
```

Or from outside the container:

```bash
# Build and run with trigger
docker-compose run --rm email-notifier python main.py --trigger --email test@example.com
```

## Configuration

Set the following environment variables:

### Email Settings

- `SMTP_HOST` - SMTP server hostname (default: `smtp.gmail.com`)
- `SMTP_PORT` - SMTP server port (default: `587`)
- `SMTP_USER` - SMTP username/email
- `SMTP_PASSWORD` - SMTP password or app password
- `SMTP_FROM_EMAIL` - Sender email address (defaults to `SMTP_USER`)
- `SMTP_FROM_NAME` - Sender name (default: `AI Scrum Master`)

### Scheduling

- `EMAIL_SEND_TIME` - Time to send emails (format: `HH:MM`, default: `09:00`)
- `EMAIL_TIMEZONE` - Timezone for scheduling (default: `UTC`)

### Behavior

- `TARGET_EMAIL` - If set, sends emails only to this address (useful for testing)
- `DEADLINE_DAYS_AHEAD` - Number of days ahead to show deadlines (default: `7`)

## Email Content

Each email includes:

### Upcoming Deadlines

- Action item description
- Owner (if assigned)
- Priority (if set)
- Due date with days remaining
- Color-coded urgency (red for ≤1 day, yellow for ≤3 days)
- Associated meeting information

### Last Meeting Summary (Contextualized)

- **Meeting Details**: Date, platform, meeting ID, goal, sentiment
- **Summary**: Full meeting summary text
- **Blockers**: List of blockers identified during the meeting
- **Deadlines**: Deadlines mentioned in the meeting metadata
- **Key Highlights**: Top 5 speaker highlights with labels (обновление, решение, блокер, другое)
- **Transcript Statistics**: Number of transcript segments
- **Insights**: Meeting insights and dashboard data from the meeting

## Gmail Setup

To use Gmail SMTP:

1. Enable 2-Factor Authentication on your Google account
2. Generate an App Password:

   - Go to Google Account → Security → 2-Step Verification → App passwords
   - Create a new app password for "Mail"
   - Use this password as `SMTP_PASSWORD`

3. Set environment variables:
   ```bash
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASSWORD=your-app-password
   ```

## Testing

### Quick Test

```bash
# Set target email in .env
TARGET_EMAIL=your-test@example.com

# Start service (runs initial check)
docker-compose up email-notifier

# Or trigger manually
docker-compose run --rm email-notifier python main.py --trigger --email your-test@example.com
```

### Check Logs

```bash
docker-compose logs -f email-notifier
```

## Troubleshooting

### Emails not sending

1. Check SMTP credentials are correct
2. Verify SMTP server allows connections from your IP
3. For Gmail, ensure App Password is used (not regular password)
4. Check logs: `docker-compose logs email-notifier`

### No deadlines showing

- Verify action items have `due_date` set
- Check that `due_date` is within `DEADLINE_DAYS_AHEAD` days
- Ensure action items are not marked as `completed`

### No meeting summaries

- Verify meetings have `status = 'completed'`
- Check that `summary_state = 'completed'`
- Ensure `meeting_metadata.summary` is not empty

### Manual trigger not working

- Ensure you're using `--trigger` flag
- Check container is running: `docker ps | grep email-notifier`
- Verify database connection is working
- Check logs for errors

## Command Reference

```bash
# Scheduled mode (default)
python main.py

# Manual trigger - send to all users
python main.py --trigger

# Manual trigger - send to specific email
python main.py --trigger --email user@example.com

# Help
python main.py --help
```

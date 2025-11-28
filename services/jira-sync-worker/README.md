# Jira Sync Worker

Automatically syncs meeting insights (action items, blockers, deadlines) to Jira issues.

## Overview

The Jira Sync Worker polls PostgreSQL for meetings with completed insights (`summary_state='completed'`) and creates corresponding Jira issues for:

- **Action Items** → Jira Tasks with `action-item` label
- **Blockers** → Jira Tasks with `blocker` label (High priority)
- **Critical Deadlines** → Jira Tasks with `deadline` label (High priority)

## Configuration

### Required Environment Variables

```bash
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_USER_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-jira-api-token  # Get from: https://id.atlassian.com/manage-profile/security/api-tokens
JIRA_PROJECT_KEY=PROJ  # Your Jira project key
```

### Optional Configuration

```bash
# Issue Types
JIRA_ISSUE_TYPE_TASK=Task
JIRA_ISSUE_TYPE_BLOCKER=Task
JIRA_ISSUE_TYPE_DEADLINE=Task

# Labels
JIRA_LABEL_BLOCKER=blocker
JIRA_LABEL_DEADLINE=deadline
JIRA_LABEL_ACTION_ITEM=action-item
JIRA_LABEL_MEETING=meeting-generated

# Priority Mapping
JIRA_PRIORITY_HIGH=High
JIRA_PRIORITY_MEDIUM=Medium
JIRA_PRIORITY_LOW=Low

# Worker Settings
JIRA_SYNC_POLL_INTERVAL=60  # seconds
JIRA_SYNC_BATCH_SIZE=1
JIRA_DRY_RUN=false  # Set to 'true' to log without creating issues

# Rate Limiting (Jira free tier: 500 requests/10min)
JIRA_RATE_LIMIT_REQUESTS=500
JIRA_RATE_LIMIT_WINDOW=600
JIRA_RETRY_MAX_ATTEMPTS=3
JIRA_RETRY_BACKOFF_BASE=2.0
```

## Team Member Mapping

To assign Jira issues to team members, add Jira account IDs to `team_roster.txt`:

```
Анна Ким — Продакт-оунер — ... | jira_account_id:5d1234567890abcdef123456
Бекзат Нургалиев — Технический лидер — ... | jira_account_id:5dabcdef1234567890abcdef
```

If a team member doesn't have a Jira account ID in the roster, the worker will attempt to find them via Jira's user search API by display name.

## How It Works

1. **Polling**: Worker polls PostgreSQL every `JIRA_SYNC_POLL_INTERVAL` seconds for meetings with:
   - `summary_state = 'completed'` (insights generated)
   - `data->'insights_ru'` exists
   - `data->>'jira_sync_state'` IS NULL or = 'failed'

2. **Issue Creation**: For each meeting:
   - Creates Jira issues for action items, blockers, and deadlines
   - Resolves assignees via team roster mapping or Jira user search
   - Maps priorities from Russian (высокий/средний/низкий) to Jira priorities

3. **Status Tracking**: Updates `meeting.data` with:
   ```json
   {
     "jira_sync_state": "success" | "failed" | "processing",
     "jira_issues": [
       {
         "local_id": 123,
         "jira_key": "PROJ-456",
         "jira_id": "10001",
         "type": "action_item" | "blocker" | "deadline"
       }
     ],
     "jira_synced_at": "2025-01-15T10:30:00Z",
     "jira_error": "..."  // if failed
   }
   ```

## Dry Run Mode

Set `JIRA_DRY_RUN=true` to test without creating actual Jira issues. The worker will log all operations but won't call the Jira API.

## Usage

### Start the Worker

```bash
# Build and start
make build-jira-sync
make up-jira-sync

# Or start with docker-compose
docker compose up -d jira-sync-worker
```

### View Logs

```bash
make logs-jira-sync
# Or
docker compose logs -f jira-sync-worker
```

### Manual Retry

To retry a failed sync, update the meeting's `jira_sync_state` in PostgreSQL:

```sql
UPDATE meetings 
SET data = jsonb_set(data, '{jira_sync_state}', 'null'::jsonb)
WHERE id = <meeting_id>;
```

## Error Handling

- **Rate Limiting**: Respects Jira API rate limits (500 requests/10min on free tier)
- **Retry Logic**: Exponential backoff for server errors (5xx)
- **User Resolution**: Falls back to Jira user search if roster mapping fails
- **Partial Success**: Continues creating issues even if some fail

## Example Jira Issues Created

### Action Item
- **Summary**: `Иван: Реализовать интеграцию с внешними API`
- **Type**: Task
- **Labels**: `action-item`, `meeting-generated`
- **Assignee**: Resolved from team roster
- **Due Date**: From action item's `due_date`
- **Priority**: Mapped from Russian priority

### Blocker
- **Summary**: `Blocker: Нужен доступ к Jira`
- **Type**: Task
- **Labels**: `blocker`, `meeting-generated`
- **Priority**: High (always)
- **Description**: Includes impact and proposed action

### Deadline
- **Summary**: `Deadline: Sprint ends Dec 5`
- **Type**: Task
- **Labels**: `deadline`, `meeting-generated`
- **Priority**: High (always)
- **Due Date**: From deadline's `date` field
- **Description**: Includes risk and dependencies

## Troubleshooting

### Issues Not Created

1. Check logs: `make logs-jira-sync`
2. Verify Jira credentials in `.env`
3. Check meeting has insights: `SELECT data->'insights_ru' FROM meetings WHERE id = X;`
4. Verify sync state: `SELECT data->'jira_sync_state' FROM meetings WHERE id = X;`

### User Assignment Fails

1. Add Jira account IDs to `team_roster.txt`
2. Or ensure team member names match Jira display names
3. Check Jira user search API permissions

### Rate Limit Errors

- Reduce `JIRA_SYNC_BATCH_SIZE` to 1
- Increase `JIRA_SYNC_POLL_INTERVAL`
- Check Jira API rate limit status


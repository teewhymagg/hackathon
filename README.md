# AI Scrum Master - Meeting Insights Platform

An intelligent meeting transcription and AI insights platform that automatically extracts structured information from meetings, generates actionable insights, and syncs with Jira for project management.

## Overview

This platform provides:

- 🤖 **Automated Meeting Bots** - Join Google Meet/Teams meetings automatically
- 🎤 **Real-time Transcription** - Convert audio to text using OpenAI Whisper
- 🧠 **AI-Powered Insights** - Extract deadlines, tasks, blockers, and action items using LLM
- 📊 **Structured Analytics** - View meeting insights in Streamlit dashboard
- 🔗 **Jira Integration** - Automatically sync tasks and blockers to Jira
- 💬 **RAG Chat Interface** - Semantic search across all meeting transcripts
- 📧 **Email Notifications** - Get notified about upcoming deadlines

## Architecture

### Core Services

```
hackathon/
  docker-compose.yml              # Full stack orchestration
  Makefile                        # Helper commands
  env-example.cpu                # Environment template
  services/
    api-gateway/                 # REST/WebSocket entry point
    admin-api/                   # User & token management
    bot-manager/                 # Bot orchestration & lifecycle
    hackathon-bot/               # Chromium-based meeting bot
    WhisperLive/                 # Real-time transcription server
    transcription-collector/      # Transcript ingestion & storage
    meeting-insights-worker/     # AI insights generation + RAG API
    meeting-insights-ui/         # Streamlit dashboard
    jira-sync-worker/            # Jira synchronization
    email-notifier/              # Email notifications
  libs/
    shared-models/               # Shared database models & schemas
```

### Technology Stack

- **Core**: FastAPI, OpenAI (GPT-5-nano, GPT-4o-transcribe)
- **Infra**: Docker Compose, Playwright
- **Data**: PostgreSQL (pgvector), Redis (Streams, Pub/Sub)
- **Integrations**: Jira REST API, Google Meet
- **Frontend**: Streamlit
- **Security**: API Key Authentication, On-Premise Ready

## Quickstart

### 1. Bootstrap Environment

```bash
cd hackathon
make init   # Copies env-example.cpu -> .env
```

Edit `.env` and configure:

- `ADMIN_API_TOKEN` - Shared secret for admin operations
- `OPENAI_API_KEY` - Required for transcription and insights (ChatGPT-4o Transcribe)
- `JIRA_BASE_URL`, `JIRA_USER_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` - For Jira sync (optional)
- `SMTP_*` variables - For email notifications (optional)

### 2. Build Bot Image

```bash
make build-bot
```

### 3. Start Services

```bash
make up
```

Services will be available at:

- **API Gateway**: `http://localhost:18056`
- **Admin API**: `http://localhost:18057/docs`
- **Meeting Insights UI**: `http://localhost:18501`
- **Transcription Collector**: `http://localhost:18123/health`
- **PostgreSQL**: `localhost:15438`
- **Jira Sync API**: `http://localhost:18004`

### 4. Create User & API Token

```bash
# Create user
curl -X POST http://localhost:18056/admin/users \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: $ADMIN_API_TOKEN" \
  -d '{"email":"scrum@example.com","max_concurrent_bots":2}'

# Generate API token
curl -X POST http://localhost:18056/admin/users/1/tokens \
  -H "X-Admin-API-Key: $ADMIN_API_TOKEN"
```

Save the returned `token` as your `X-API-Key`.

### 5. Launch Bot for Meeting

```bash
curl -X POST http://localhost:18056/bots \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $USER_TOKEN" \
  -d '{"platform":"google_meet","native_meeting_id":"xxx-xxxx-xxx"}'
```

The bot will:

1. Join the meeting automatically
2. Capture audio and transcribe in real-time
3. Store transcripts in PostgreSQL
4. Generate insights after meeting ends
5. Sync to Jira (if configured)

### 6. View Meeting Insights

Open the Streamlit dashboard:

```
http://localhost:18501
```

Features:

- Meeting overview with sentiment analysis
- Responsible people and workload assessment
- Critical deadlines and dependencies
- Blockers and proposed actions
- Action items with owners and priorities
- Speaker highlights
- RAG chat interface for semantic search

## Key Features

### 🤖 Automated Meeting Transcription

- Real-time audio capture from Google Meet/Teams
- OpenAI Whisper transcription (or faster-whisper fallback)
- Hallucination filtering for speech recognition errors
- Speaker identification and language detection

### 🧠 AI-Powered Insights Extraction

Automatically extracts from meeting transcripts:

- **Deadlines** - Critical dates with owners and risks
- **Tasks** - Action items with assignments and priorities
- **Blockers** - Issues blocking progress with impact analysis
- **Task Decomposition** - Epic tasks broken into subtasks
- **Team Coverage** - Workload assessment per team member
- **Sentiment Analysis** - Meeting tone (positive/neutral/negative)
- **Missing Elements** - Unassigned tasks and unclear requirements

### 📊 Structured Data Storage

- PostgreSQL with pgvector for semantic search
- Embeddings for transcript segments and insights
- Meeting metadata, action items, speaker highlights
- RAG-ready data structure

### 🔗 Jira Integration

- Automatic sync of action items, blockers, and deadlines
- Task type classification (Epic, Feature, Task, Bug)
- Team member mapping to Jira accounts
- Priority and label assignment

### 💬 RAG Chat Interface

- Semantic search across all meetings
- Meeting-specific queries with insights context
- Conversation history support
- Hallucination filtering in responses

### 📧 Email Notifications

- Upcoming deadline reminders
- Meeting summary notifications
- Configurable scheduling

## Data Flow

1. **Bot Launch** → User requests bot → Bot Manager creates container → Bot joins meeting
2. **Transcription** → Bot captures audio → WhisperLive transcribes → Redis Streams → Transcription Collector stores in PostgreSQL
3. **Insights Generation** → Meeting completes → Insights Worker processes → LLM extracts structured data → Stored in database
4. **Jira Sync** → Insights Worker triggers → Jira Sync Worker creates issues → Tasks synced to Jira
5. **RAG Query** → User queries → RAG API searches embeddings → LLM generates answer with context

## Configuration

### Environment Variables

**Required:**

- `ADMIN_API_TOKEN` - Admin authentication
- `OPENAI_API_KEY` - OpenAI API key for transcription/insights

**Optional:**

- `OPENAI_SUMMARY_MODEL` - Model for insights (default: `gpt-5-nano`)
- `OPENAI_EMBEDDING_MODEL` - Embedding model (default: `text-embedding-3-small`)
- `WHISPER_BACKEND` - `openai` or `faster_whisper` (default: `openai`)
- `JIRA_*` - Jira integration settings
- `SMTP_*` - Email notification settings

See `env-example.cpu` for full configuration options.

## API Usage

### Get Transcripts

```bash
# REST API
curl -H "X-API-Key: $USER_TOKEN" \
  http://localhost:18056/transcripts/google_meet/xxx-xxxx-xxx

# WebSocket (real-time)
ws://localhost:18056/ws?api_key=$USER_TOKEN
# Send: {"action":"subscribe","meetings":[{"platform":"google_meet","native_id":"xxx-xxxx-xxx"}]}
```

### Query RAG

```bash
curl -X POST http://localhost:18002/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Какие блокеры обсуждались?",
    "mode": "global",
    "conversation": []
  }'
```

### Trigger Jira Sync

```bash
curl -X POST http://localhost:18004/trigger \
  -H "Content-Type: application/json" \
  -d '{"meeting_id": 1}'
```

## Customization

- **Transcription Backend**: Switch between OpenAI and faster-whisper
- **LLM Models**: Configure different models for insights and RAG
- **Jira Issue Types**: Customize task type mappings
- **Team Roster**: Update `team_roster.txt` for team member context
- **Email Templates**: Customize notification templates

## Troubleshooting

- **View logs**: `docker compose logs -f` or `make logs`
- **Stop services**: `make down` (add `-v` to remove volumes)
- **Database migrations**: Run automatically on startup
- **Bot issues**: Check `bot-manager` logs for container lifecycle
- **Transcription issues**: Verify `OPENAI_API_KEY` and `WHISPER_BACKEND` settings

## Documentation

- `PROJECT_OVERVIEW.md` - Detailed architecture documentation
- `docs/` - Additional guides and setup instructions
- `project_assessment.md` - System performance assessment
- `project_assessment_verification.md` - Codebase verification

## License

See LICENSE file for details.

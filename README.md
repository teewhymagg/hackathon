# Hackathon Stack (AI Scrum Master)

A trimmed, self-contained copy of the hackathon_bot meeting bot pipeline tailored for quick experimentation. It keeps only the services required to drop a bot into Google Meet/Teams, capture audio, and stream transcripts to downstream AI agents.

## Contents

```
hackathon/
  docker-compose.yml        # Minimal stack definition
  Makefile                  # Helper targets (init, build, up, down, logs)
  env-example.cpu           # CPU-friendly defaults (.env template)
  services/
    api-gateway/            # REST/WebSocket entry point
    admin-api/              # User + token management
    bot-manager/            # Meeting orchestration & bot lifecycle
    transcription-collector/# Transcript ingestion + storage
    WhisperLive/            # Faster-Whisper real-time server (CPU profile)
    hackathon-bot/          # Chromium-based meeting bot
  libs/
    shared-models/          # Alembic + SQLAlchemy models shared by APIs
  alembic.ini               # Mounted by transcription-collector
```

## Quickstart

1. **Bootstrap `.env`**

   ```bash
   cd hackathon
   make init   # copies env-example.cpu -> .env (only once)
   ```

   Fill in:

   - `ADMIN_API_TOKEN`: shared secret for admin endpoints + MeetingToken signing.
   - `OPENAI_API_KEY`: required for the default `openai` transcription backend (ChatGPT-4o Transcribe).
   - Optional: tune `WHISPER_BACKEND` (defaults to `openai`) and the chunking knobs (`OPENAI_TRANSCRIBE_*`) if you need local Whisper fallback.
   - Optional overrides (ports, Whisper model size, etc.).

2. **Build the meeting bot image**

   ```bash
   make build-bot
   ```

   This tags the local image as `hackathon_bot:hackathon`, matching the compose default.

3. **Start the stack**

   ```bash
   make up
   ```

   Services exposed locally:

   - API Gateway: `http://localhost:18056`
   - Admin API docs: `http://localhost:18057/docs`
   - Transcription Collector: `http://localhost:18123/health`
   - Postgres: `localhost:15438`

4. **Provision a user + API token**
   Use `docs/self-hosted-management.md` (copied from the root project) or run:

   ```bash
   curl -X POST http://localhost:18056/admin/users \
     -H "Content-Type: application/json" \
     -H "X-Admin-API-Key: $ADMIN_API_TOKEN" \
     -d '{"email":"scrum@example.com","max_concurrent_bots":2}'

   curl -X POST http://localhost:18056/admin/users/1/tokens \
     -H "X-Admin-API-Key: $ADMIN_API_TOKEN"
   ```

   Save the returned `token` as your `X-API-Key` for client calls.

5. **Request a bot**

   ```bash
   curl -X POST http://localhost:18056/bots \
     -H "Content-Type: application/json" \
     -H "X-API-Key: $USER_TOKEN" \
     -d '{"platform":"google_meet","native_meeting_id":"xxx-xxxx-xxx"}'
   ```

   Logs from `bot-manager` will show the container lifecycle; transcripts stream through `/transcripts/...` or the WebSocket `/ws` endpoint.

6. **Consume transcripts**
   - REST polling: `GET /transcripts/{platform}/{native_id}`
   - Real-time stream: open a WS client and send `{"action":"subscribe", ...}` as documented in `docs/websocket.md`.

## Customization Tips

- Update `docker-compose.yml` to switch `whisperlive` to GPU mode or add extra services (e.g., your AI Scrum Master microservice).
- Tune the transcription backend: `WHISPER_BACKEND=openai` (default) streams PCM to ChatGPT-4o Transcribe via `OPENAI_API_KEY`; set it to `faster_whisper` to fall back to the bundled local model and ignore the OpenAI knobs.
- Extend `Makefile` with helper targets (database migrations, log tailing, etc.).
- Keep parity with the upstream hackathon_bot sources by periodically syncing `services/*` and `libs/shared-models` from the root repo.
- Build your hackathon-specific code (e.g., standup summarizer) alongside this directory to keep a clean separation from the upstream project.

## Troubleshooting

- `docker compose logs -f` (or `make logs`) to inspect all services.
- `make down` tears everything down; add `-v` to prune volumes if you need a fresh DB.
- Ensure Chrome dependencies for `hackathon-bot` are satisfied on first run (`fresh_setup.sh` in the root repo installs fonts & playwright browsers if needed).

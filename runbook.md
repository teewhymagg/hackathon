# hackathon_bot Runbook

End-to-end instructions for running the trimmed hackathon stack, provisioning users, launching a meeting bot, and consuming the resulting transcripts for your AI Scrum Master workload.

---

## 1. Prerequisites

- macOS/Linux host with Docker Engine ≥ 24 and the Compose plugin (`docker compose version`).
- At least 12 GB free disk space (Chromium + Whisper models + Postgres).
- (Optional) `make` for the helper targets defined in `hackathon/Makefile`.

> **Tip:** If you are on Apple Silicon, the stack runs entirely on CPU. No external Whisper API keys are required; `WhisperLive` bundles `faster-whisper`.

---

## 2. Directory layout recap

```
hackathon/
  docker-compose.yml        # Service definitions
  Makefile                  # init/build/up/down helpers
  env-example.cpu           # Template .env
  services/
    api-gateway/            # REST + WebSocket surface for clients
    admin-api/              # Admin-only user/token management
    bot-manager/            # Launches Chromium bots via Docker
    transcription-collector/# Persists transcript stream to Postgres
    WhisperLive/            # Real-time speech-to-text server
    hackathon-bot/          # Chromium/Playwright meeting bot image
  libs/shared-models/       # SQLAlchemy models + Alembic
  docs/                     # Guides (this file, WebSocket spec, etc.)
```

---

## 3. Environment setup

```bash
cd hackathon
make init          # copies env-example.cpu -> .env (first run only)
```

Open `.env` and set at least:

| Variable                        | Purpose                                                                                        |
| ------------------------------- | ---------------------------------------------------------------------------------------------- |
| `ADMIN_API_TOKEN`               | Shared secret used by Admin API + bot-manager signing                                          |
| `OPENAI_API_KEY`                | Required for the default ChatGPT-4o transcription backend (`WHISPER_BACKEND=openai`)           |
| `WHISPER_BACKEND`               | Choose `openai` (default) or `faster_whisper` if you need the bundled local model              |
| `OPENAI_TRANSCRIBE_*`           | Optional knobs for chunk length, retries, prompts when using OpenAI                            |
| `TEAM_ROSTER_PATH` (optional)   | Path (inside containers) to a txt file with командные роли; defaults to `/app/team_roster.txt` |
| `BOT_IMAGE_NAME` (optional)     | Defaults to `hackathon_bot:hackathon`; override if you publish elsewhere                       |
| `WHISPER_MODEL_SIZE` (optional) | `tiny`, `base`, `small`, … depending on CPU budget                                             |

You can keep the provided ports unless they clash locally.

---

## 4. Build + start the stack

1. **Build the bot image** (installs Playwright/Chromium once):

   ```bash
   make build-bot
   ```

2. **Start services**:

   ```bash
   make up
   ```

   Services exposed locally:

   - API Gateway: `http://localhost:18056`
   - Admin API (FastAPI docs): `http://localhost:18057/docs`
   - Transcription Collector health: `http://localhost:18123/health`
   - Postgres: `localhost:15438`
   - `whisperlive` now defaults to the OpenAI backend—double-check `OPENAI_API_KEY` is set before calling `make up`, otherwise requests will fail with 401s from the transcription bridge.
   - Meeting Insights UI: `http://localhost:18501`
   - A one-shot `db-migrate` service now runs automatically to apply Alembic migrations before any DB client starts, so fresh volumes “just work.”

   > **Service helpers:**
   >
   > - `make build-services` rebuilds `whisperlive`, `meeting-insights-worker`, and `meeting-insights-ui`.
   > - `make up-whisperlive` launches just the WhisperLive container (if you need to start it separately).
   > - `make up-insights` starts the meeting insights worker + Streamlit dashboard (if you need to start them separately).

3. **All services start automatically**. `make up` now starts all services including WhisperLive, meeting-insights-worker, and meeting-insights-ui.

4. **Verify**:
   ```bash
   docker compose -f docker-compose.yml --env-file .env ps
   docker compose -f docker-compose.yml --env-file .env logs -f api-gateway
   docker compose -f docker-compose.yml --env-file .env logs -f whisperlive
   ```

---

## 5. Register a user & issue an API token

All admin operations go through the API Gateway using your `ADMIN_API_TOKEN`.

```bash
export ADMIN_API_TOKEN=changeme-from-env

# Create a user (id will be 1 on a fresh DB)
curl -X POST http://localhost:18056/admin/users \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: $ADMIN_API_TOKEN" \
  -d '{"email":"scrum@example.com","max_concurrent_bots":2}'

# Issue a client token for that user
curl -X POST http://localhost:18056/admin/users/1/tokens \
  -H "X-Admin-API-Key: $ADMIN_API_TOKEN"
```

Save the returned `token` value; it becomes the `X-API-Key` header for all client calls (bot launch, transcript fetch, etc.).

---

## 6. Launch a meeting bot

Send a POST to `/bots` via the API Gateway with your user token:

```bash
export USER_TOKEN="paste-token-from-previous-step"

curl -X POST http://localhost:18056/bots \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $USER_TOKEN" \
  -d '{
        "platform": "google_meet",
        "native_meeting_id": "fau-bvsd-owz",
        "display_name": "Scrum Recorder"
      }'
```

Key fields:

- `platform`: `google_meet` or `microsoft_teams`.
- `native_meeting_id`: the meeting code (e.g., `nox-nvbs-wpk`).
- Optional metadata such as `display_name`, `passcode`, `start_url`.

### Monitor the launch

- `docker compose ... logs -f bot-manager` — shows container lifecycle, meeting admission flow, WhisperLive connection attempts.
- `docker compose ... logs -f hackathon-bot` — view Chromium/Playwright logs (container name follows `hackathon_bot-bot-<uuid>`).
- `docker compose ... logs -f whisperlive` — look for `New client connected` and `LANGUAGE_DETECTION` lines confirming audio is flowing.

When the bot joins successfully you will see `status: active` in the `/bots/{id}` response and a flurry of WhisperLive WebSocket connections ending in `SERVER_READY`.

---

## 7. Consume transcripts

### REST (polling)

```bash
curl -H "X-API-Key: $USER_TOKEN" \
     http://localhost:18056/transcripts/google_meet/pnz-iyod-ftf
```

Response contains meeting metadata plus the ordered `segments` array (`start`, `end`, `text`, `language`, timestamps).

### WebSocket (real-time)

1. Connect: `ws://localhost:18056/ws?api_key=$USER_TOKEN`
2. Send a subscribe message (see `docs/websocket.md` for the schema):
   ```json
   {
     "action": "subscribe",
     "platform": "google_meet",
     "native_meeting_id": "nox-nvbs-wpk"
   }
   ```
3. Streamed payloads contain incremental transcripts and completion events—ideal for piping into your AI Scrum Master summarizer.

---

## 8. Shutting down & cleanup

```bash
make down                    # stop services, keep volumes
make down VOLUMES=true       # or `docker compose ... down -v` for a clean DB
docker image rm hackathon_bot:hackathon  # optional image cleanup
```

If you changed Compose project names (`COMPOSE_PROJECT_NAME`), adjust the commands accordingly.

---

## 9. Troubleshooting checklist

- **Bot never leaves “pending”**: check `bot-manager` logs for admin token mismatch, or ensure Docker Desktop has >4 GB RAM.
- **WhisperLive WebSocket error code 1006**: confirm the container is running (`docker compose ... ps whisperlive`) and that `WHISPER_LIVE_URL` in `bot-manager` points to `ws://whisperlive:9090/ws`.
- **`UndefinedTableError` when creating users**: the shared models migrate automatically at container startup; if Postgres was reset midway, restart the `admin-api` and `transcription-collector` containers to re-run `init_db()`.
- **Admin curl 401**: make sure `X-Admin-API-Key` matches the `ADMIN_API_TOKEN` stored in `.env` and exported into your shell (`export ADMIN_API_TOKEN=...`).

With these steps you have a fully functioning meeting-ingestion loop: launch bots, receive transcripts, and hand them off to your AI Scrum Master logic for summarization, action items, or status reports.

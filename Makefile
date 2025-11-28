COMPOSE ?= docker compose -f docker-compose.yml
ENV_FILE ?= .env
BOT_IMAGE_NAME ?= hackathon_bot:hackathon

.PHONY: init
init:
	cp -n env-example.cpu .env || true
	@echo "✓ .env ready. Configure API tokens and meeting defaults."

.PHONY: build-bot
build-bot:
	docker build -t hackathon_bot:hackathon services/hackathon-bot/core

.PHONY: up
up:
	BOT_IMAGE_NAME=$(BOT_IMAGE_NAME) $(COMPOSE) --env-file $(ENV_FILE) up -d --build

.PHONY: down
down:
	$(COMPOSE) --env-file $(ENV_FILE) down

.PHONY: logs
logs:
	$(COMPOSE) --env-file $(ENV_FILE) logs -f

.PHONY: ps
ps:
	$(COMPOSE) --env-file $(ENV_FILE) ps

.PHONY: build-services
build-services:
	$(COMPOSE) --env-file $(ENV_FILE) build whisperlive meeting-insights-worker meeting-insights-ui email-notifier jira-sync-worker

.PHONY: build-insights-worker
build-insights-worker:
	$(COMPOSE) --env-file $(ENV_FILE) build meeting-insights-worker

.PHONY: build-insights-ui
build-insights-ui:
	$(COMPOSE) --env-file $(ENV_FILE) build meeting-insights-ui

.PHONY: build-insights
build-insights: build-insights-worker build-insights-ui
	@echo "✓ Built meeting insights services (worker + UI)"

.PHONY: build-jira-sync
build-jira-sync:
	$(COMPOSE) --env-file $(ENV_FILE) build jira-sync-worker
	@echo "✓ Built Jira sync worker"

.PHONY: up-whisperlive
up-whisperlive:
	$(COMPOSE) --env-file $(ENV_FILE) --profile cpu up -d whisperlive

.PHONY: up-insights
up-insights:
	$(COMPOSE) --env-file $(ENV_FILE) up -d meeting-insights-worker meeting-insights-ui

.PHONY: up-email-notifier
up-email-notifier:
	$(COMPOSE) --env-file $(ENV_FILE) up -d email-notifier

.PHONY: trigger-email
trigger-email:
	$(COMPOSE) --env-file $(ENV_FILE) run --rm email-notifier python main.py --trigger

.PHONY: trigger-email-to
trigger-email-to:
	@read -p "Enter email address: " email; \
	$(COMPOSE) --env-file $(ENV_FILE) run --rm email-notifier python main.py --trigger --email $$email

.PHONY: logs-email
logs-email:
	$(COMPOSE) --env-file $(ENV_FILE) logs -f email-notifier

.PHONY: up-jira-sync
up-jira-sync:
	$(COMPOSE) --env-file $(ENV_FILE) up -d jira-sync-worker

.PHONY: restart-jira-sync
restart-jira-sync:
	$(COMPOSE) --env-file $(ENV_FILE) restart jira-sync-worker

.PHONY: logs-jira-sync
logs-jira-sync:
	$(COMPOSE) --env-file $(ENV_FILE) logs -f jira-sync-worker

.PHONY: stop-jira-sync
stop-jira-sync:
	$(COMPOSE) --env-file $(ENV_FILE) stop jira-sync-worker

.PHONY: build-and-up-jira-sync
build-and-up-jira-sync: build-jira-sync up-jira-sync
	@echo "✓ Jira sync worker built and started"

.PHONY: reset-jira-sync
reset-jira-sync:
	@read -p "Enter meeting ID (or 'all' for all meetings): " meeting_id; \
	if [ "$$meeting_id" = "all" ]; then \
		docker exec -i hackathon_bot_stack-postgres-1 psql -U postgres -d hackathon_bot -c \
		"UPDATE meetings SET data = jsonb_set(COALESCE(data, '{}'::jsonb), '{jira_sync_state}', 'null'::jsonb) WHERE data->>'jira_sync_state' = 'success';"; \
	else \
		docker exec -i hackathon_bot_stack-postgres-1 psql -U postgres -d hackathon_bot -c \
		"UPDATE meetings SET data = jsonb_set(COALESCE(data, '{}'::jsonb), '{jira_sync_state}', 'null'::jsonb) WHERE id = $$meeting_id;"; \
	fi
	@echo "✓ Reset Jira sync state (Note: This only resets DB state, doesn't delete Jira issues)"

.PHONY: delete-jira-issues
delete-jira-issues:
	@echo "⚠️  This will DELETE all Jira issues with 'meeting-generated' label!"
	@python scripts/delete_jira_test_issues.py

.PHONY: delete-all-jira-issues
delete-all-jira-issues:
	@echo "⚠️  WARNING: This will DELETE ALL issues in your Jira project!"
	@read -p "Type 'DELETE ALL' to confirm: " confirm; \
	if [ "$$confirm" = "DELETE ALL" ]; then \
		python scripts/delete_jira_test_issues.py --all; \
	else \
		echo "Cancelled"; \
	fi

.PHONY: clean-jira-test
clean-jira-test: delete-jira-issues reset-jira-sync
	@echo "✓ Deleted meeting-generated Jira issues and reset sync state"

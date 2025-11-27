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
	$(COMPOSE) --env-file $(ENV_FILE) build whisperlive meeting-insights-worker meeting-insights-ui

.PHONY: up-whisperlive
up-whisperlive:
	$(COMPOSE) --env-file $(ENV_FILE) --profile cpu up -d whisperlive

.PHONY: up-insights
up-insights:
	$(COMPOSE) --env-file $(ENV_FILE) up -d meeting-insights-worker meeting-insights-ui

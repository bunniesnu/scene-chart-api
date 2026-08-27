PROJECT_NAME ?= scene-chart-api
DOCKER_COMPOSE_FILE ?= ./docker/docker-compose.yml
COMPOSE := docker compose -f $(DOCKER_COMPOSE_FILE) --project-directory . -p "$(PROJECT_NAME)"
LOCAL_PROJECT_NAME ?= scene-chart-api-local
LOCAL_DOCKER_COMPOSE_FILE ?= ./docker/docker-compose.local.yml
LOCAL_COMPOSE := docker compose -f $(LOCAL_DOCKER_COMPOSE_FILE) --project-directory . -p "$(LOCAL_PROJECT_NAME)"

.PHONY: build stop run local revision logs main

build:
	COMPOSE_BAKE=true $(COMPOSE) build

stop:
	$(COMPOSE) down

run: build stop
	$(COMPOSE) up -d

local:
	COMPOSE_BAKE=true $(LOCAL_COMPOSE) build
	$(LOCAL_COMPOSE) down
	$(LOCAL_COMPOSE) up -d

revision:
	@test -n "$(MSG)" || (echo "Usage: make revision MSG='message'" && exit 1)
	./scripts/revision.sh "$(MSG)"

logs:
	$(COMPOSE) logs -f

main: build stop
	$(COMPOSE) up -d app
	$(COMPOSE) exec app uv run --no-sync main.py
	$(COMPOSE) down
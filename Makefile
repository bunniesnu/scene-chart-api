PROJECT_NAME ?= scene-chart-api
DOCKER_COMPOSE_FILE ?= ./docker/docker-compose.yml
LOCAL_PROJECT_NAME ?= scene-chart-api-local
LOCAL_DOCKER_COMPOSE_FILE ?= ./docker/docker-compose.local.yml

ifeq ($(ENV),local)
	COMPOSE := docker compose -f $(LOCAL_DOCKER_COMPOSE_FILE) --project-directory . -p "$(LOCAL_PROJECT_NAME)"
else
	COMPOSE := docker compose -f $(DOCKER_COMPOSE_FILE) --project-directory . -p "$(PROJECT_NAME)"
endif

.PHONY: build stop run logs revision main

build:
	COMPOSE_BAKE=true $(COMPOSE) build

stop:
	$(COMPOSE) down

run: build stop
	$(COMPOSE) up -d

logs:
	$(COMPOSE) logs -f

revision:
	@test -n "$(MSG)" || (echo "Usage: make revision MSG='message'" && exit 1)
	LOCAL_PROJECT_NAME=$(LOCAL_PROJECT_NAME) LOCAL_DOCKER_COMPOSE_FILE=$(LOCAL_DOCKER_COMPOSE_FILE) ./scripts/revision.sh "$(MSG)"

main: build stop
	$(COMPOSE) up -d app
	$(COMPOSE) exec app uv run --no-sync main.py
	$(COMPOSE) down
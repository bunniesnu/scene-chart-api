PROJECT_NAME ?= scene-chart-api
DOCKER_COMPOSE_FILE ?= ./docker/docker-compose.yml
COMPOSE := docker compose -f $(DOCKER_COMPOSE_FILE) --project-directory . -p "$(PROJECT_NAME)"

.PHONY: build stop run local revision logs main

build:
	COMPOSE_BAKE=true $(COMPOSE) build

stop:
	$(COMPOSE) down

run: build stop
	$(COMPOSE) up -d

local: build stop
	PROJECT_NAME="$(PROJECT_NAME)" DOCKER_COMPOSE_FILE="$(DOCKER_COMPOSE_FILE)" ./scripts/local.sh

revision:
	@test -n "$(MSG)" || (echo "Usage: make revision MSG='message'" && exit 1)
	PROJECT_NAME="$(PROJECT_NAME)" ./scripts/revision.sh "$(MSG)"

logs:
	$(COMPOSE) logs -f

main: build stop
	$(COMPOSE) up -d app
	$(COMPOSE) exec app uv run --no-sync main.py
	$(COMPOSE) down
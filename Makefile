PROJECT_NAME ?= scene-chart-api
COMPOSE := docker compose -f ./docker/docker-compose.yml --project-directory . -p "$(PROJECT_NAME)"

.PHONY: build stop run revision logs main

build:
	COMPOSE_BAKE=true $(COMPOSE) build

stop:
	$(COMPOSE) down

run: build stop
	$(COMPOSE) up -d

revision:
	@test -n "$(MSG)" || (echo "Usage: make revision MSG='message'" && exit 1)
	PROJECT_NAME="$(PROJECT_NAME)" ./scripts/revision.sh "$(MSG)"

logs:
	$(COMPOSE) logs -f

main: build stop
	$(COMPOSE) up -d app
	$(COMPOSE) exec app uv run --no-sync main.py
	$(COMPOSE) down
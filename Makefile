ENV ?= production

PROJECT_NAME ?= scene-chart-api
DOCKER_COMPOSE_FILE ?= ./docker/docker-compose.yml
LOCAL_PROJECT_NAME ?= scene-chart-api-local
LOCAL_DOCKER_COMPOSE_FILE ?= ./docker/docker-compose.local.yml

ifeq ($(ENV),local)
	COMPOSE := docker compose -f $(LOCAL_DOCKER_COMPOSE_FILE) --project-directory . -p "$(LOCAL_PROJECT_NAME)"
else ifeq ($(ENV),production)
	COMPOSE := docker compose -f $(DOCKER_COMPOSE_FILE) --project-directory . -p "$(PROJECT_NAME)"
	COMPOSE_INIT := docker compose -f ./init/docker-compose.yml --project-directory . -p "$(PROJECT_NAME)"
else
	$(error Unknown ENV '$(ENV)'. Use 'production' or 'local')
endif

.PHONY: build certificate stop run logs restore revision main

build:
	COMPOSE_BAKE=true $(COMPOSE) build

certificate:
	set -e; \
	trap '$(COMPOSE_INIT) down' EXIT; \
	$(COMPOSE_INIT) up --exit-code-from certbot

stop:
	$(COMPOSE) down

ifeq ($(ENV),local)

run: build stop
	$(COMPOSE) up -d db
	@echo "Waiting for PostgreSQL..."
	@until $(COMPOSE) exec -T db pg_isready -U user -d db; do \
		sleep 1; \
	done
	@echo "PostgreSQL is ready."
	$(MAKE) restore
	$(COMPOSE) up -d app

else

run: build stop certificate
	$(COMPOSE) up -d

endif

logs:
	$(COMPOSE) logs -f

restore:
	@LATEST=$$(find backup -name '*.dump' -type f | sort | tail -n 1); \
	test -n "$$LATEST" || (echo "No dump file found in backup/" && exit 1); \
	echo "Restoring $$LATEST..."; \
	cat "$$LATEST" | $(COMPOSE) exec -T db \
		pg_restore \
		-U user \
		-d db \
		--no-owner \
		--no-acl \
		--clean \
		--schema=public \
		--if-exists

revision:
	@test -n "$(MSG)" || (echo "Usage: make revision MSG='message'" && exit 1)
	LOCAL_PROJECT_NAME=$(LOCAL_PROJECT_NAME) LOCAL_DOCKER_COMPOSE_FILE=$(LOCAL_DOCKER_COMPOSE_FILE) ./scripts/revision.sh "$(MSG)"

main:
	$(COMPOSE) exec app uv run --no-sync main.py
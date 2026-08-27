#!/bin/bash
set -e
cd "$(dirname "$0")/.." || exit 1

# Required input variables: LOCAL_DOCKER_COMPOSE_FILE, LOCAL_PROJECT_NAME

REVISION_FILE=""
COMPLETED=0

cleanup() {
  if [ "$COMPLETED" -eq 0 ] && [ -n "$REVISION_FILE" ] && [ -f "$REVISION_FILE" ]; then
    echo "Interrupted — removing generated revision file: $REVISION_FILE"
    rm -f "$REVISION_FILE"
  fi
  docker compose -f "$LOCAL_DOCKER_COMPOSE_FILE" down
}
trap cleanup EXIT

docker compose -f $LOCAL_DOCKER_COMPOSE_FILE down
docker volume rm ${LOCAL_PROJECT_NAME}_db_data || true
docker compose -f $LOCAL_DOCKER_COMPOSE_FILE up -d --build db

DATABASE_URL=postgresql://user:password@localhost:5432/db

# Wait for db to be ready
until docker compose -f $LOCAL_DOCKER_COMPOSE_FILE exec db pg_isready -U user -d db; do
  sleep 1
done

DATABASE_URL=$DATABASE_URL uv run alembic upgrade head
file_path=$(DATABASE_URL="$DATABASE_URL" uv run alembic revision --autogenerate -m "$1")
REVISION_FILE=$(echo "$file_path" | grep -oE '/[^ ]+\.py' | tail -n 1)

echo "Migration file generated at: $REVISION_FILE"
echo "Edit it, then press Enter to run upgrade head..."
read -r
DATABASE_URL=$DATABASE_URL uv run alembic upgrade head

COMPLETED=1
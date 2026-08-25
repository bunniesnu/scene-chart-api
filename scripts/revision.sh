#!/bin/bash
set -e
cd "$(dirname "$0")/.." || exit 1
source .env

REVISION_FILE=""
COMPLETED=0

cleanup() {
  if [ "$COMPLETED" -eq 0 ] && [ -n "$REVISION_FILE" ] && [ -f "$REVISION_FILE" ]; then
    echo "Interrupted — removing generated revision file: $REVISION_FILE"
    rm -f "$REVISION_FILE"
  fi
  rm -f "$OVERRIDE_FILE"
}
trap cleanup EXIT

DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME

DATABASE_URL=$DATABASE_URL uv run alembic upgrade head
file_path=$(DATABASE_URL="$DATABASE_URL" uv run alembic revision --autogenerate -m "$1")
REVISION_FILE=$(echo "$file_path" | grep -oE '/[^ ]+\.py' | tail -n 1)

echo "Migration file generated at: $REVISION_FILE"
echo "Edit it, then press Enter to run upgrade head..."
read -r
DATABASE_URL=$DATABASE_URL uv run alembic upgrade head

COMPLETED=1
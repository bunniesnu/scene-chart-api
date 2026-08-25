#!/bin/sh
set -eu
cd "$(dirname "$0")/.." || exit 1

TMP_DOCKER_COMPOSE_FILE="$DOCKER_COMPOSE_FILE.tmp"

cleanup() {
  if [ -n "$TMP_DOCKER_COMPOSE_FILE" ] && [ -f "$TMP_DOCKER_COMPOSE_FILE" ]; then
    echo "Cleaning up temporary docker compose file: $TMP_DOCKER_COMPOSE_FILE"
    rm -f "$TMP_DOCKER_COMPOSE_FILE"
  fi
}
trap cleanup EXIT

if grep -q '^[[:space:]]*-[[:space:]]*"8000:8000"[[:space:]]*$' "$DOCKER_COMPOSE_FILE"; then
    echo "8000:8000 already exists"
else
    awk '
    /^  app:/ {
        in_app = 1
    }

    /^  [a-zA-Z0-9_-]+:/ && !/^  app:/ {
        in_app = 0
    }

    in_app && /^    command:/ && !added {
        print "    ports:"
        print "      - \"8000:8000\""
        added = 1
    }

    {
        print
    }
    ' "$DOCKER_COMPOSE_FILE" > "$TMP_DOCKER_COMPOSE_FILE"

    echo "Added 8000:8000 to app"
fi

docker compose -f $TMP_DOCKER_COMPOSE_FILE --project-directory . -p "$PROJECT_NAME" up -d app
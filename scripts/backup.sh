#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

source .env

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT="backup/${TIMESTAMP}.dump"

mkdir -p data

docker run --rm \
  -e PGPASSWORD="$DB_PASSWORD" \
  postgres:17.6 \
  pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -Fc \
  > "$OUTPUT"

echo "Backup created: $OUTPUT"
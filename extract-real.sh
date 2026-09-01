#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")" || exit 1

source .env

DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME uv run -m extract.save
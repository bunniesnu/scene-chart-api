#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")" || exit 1

DATABASE_URL=postgresql://user:password@localhost:5432/db uv run -m extract.save
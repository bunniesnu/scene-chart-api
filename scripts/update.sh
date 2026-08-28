#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

uv remove melon-api-client
uv cache clean
uv add melon-api-client
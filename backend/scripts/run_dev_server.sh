#!/usr/bin/env bash

# Run the Flask backend with all required environment variables set.
# Usage: backend/scripts/run_dev_server.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

# Load .env if present so developers can keep secrets outside the script.
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

# Ensure critical API keys / settings are available before booting.
REQUIRED_VARS=(
  "OPENAI_API_KEY"
  "GOOGLE_AI_KEY"
)

MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    MISSING_VARS+=("$var")
  fi
done

if (( ${#MISSING_VARS[@]} > 0 )); then
  echo "Error: missing required environment variables:" >&2
  printf '  - %s\n' "${MISSING_VARS[@]}" >&2
  echo "Set them in backend/.env or your shell before running this script." >&2
  exit 1
fi

# Default local development overrides (always favor the bundled SQLite DB so reloads
# cannot fall back to Postgres and crash when no server is running).
export FAIRTESTAI_DATABASE_URL="sqlite:////${ROOT_DIR}/data/fairtestai.db"
export FAIRTESTAI_AUTO_APPLY_MIGRATIONS="${FAIRTESTAI_AUTO_APPLY_MIGRATIONS:-false}"
export FAIRTESTAI_REPORT_ANTHROPIC_MODEL="${FAIRTESTAI_REPORT_ANTHROPIC_MODEL:-claude-3-5-haiku-20241022}"
export FAIRTESTAI_REPORT_GOOGLE_MODEL="${FAIRTESTAI_REPORT_GOOGLE_MODEL:-models/gemini-2.5-flash}"
export FAIRTESTAI_REPORT_GROK_MODEL="${FAIRTESTAI_REPORT_GROK_MODEL:-grok-2-latest}"

cd "$ROOT_DIR" || exit 1
source venv_host/bin/activate

echo "Starting backend with:"
echo "  FAIRTESTAI_DATABASE_URL=$FAIRTESTAI_DATABASE_URL"
echo "  FAIRTESTAI_AUTO_APPLY_MIGRATIONS=$FAIRTESTAI_AUTO_APPLY_MIGRATIONS"
echo "  FAIRTESTAI_REPORT_ANTHROPIC_MODEL=$FAIRTESTAI_REPORT_ANTHROPIC_MODEL"
echo "  FAIRTESTAI_REPORT_GOOGLE_MODEL=$FAIRTESTAI_REPORT_GOOGLE_MODEL"
echo "  FAIRTESTAI_REPORT_GROK_MODEL=$FAIRTESTAI_REPORT_GROK_MODEL"

exec python run.py


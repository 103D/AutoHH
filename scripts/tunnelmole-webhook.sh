#!/usr/bin/env bash
set -euo pipefail

# Constants
LOG_FILE="${HOME}/.config/tunnelmole/tm.log"
BACKEND_ENV="${HOME}/Projects/AtoHH/backend/.env"
TELEGRAM_API="https://api.telegram.org"
MAX_WAIT=30

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Read credentials from backend .env
if [[ ! -f "$BACKEND_ENV" ]]; then
  echo "ERROR: $BACKEND_ENV not found" >&2
  exit 1
fi

TELEGRAM_BOT_TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' "$BACKEND_ENV" | cut -d= -f2- | tr -d '"')
TELEGRAM_WEBHOOK_SECRET=$(grep '^TELEGRAM_WEBHOOK_SECRET=' "$BACKEND_ENV" | cut -d= -f2- | tr -d '"')

if [[ -z "$TELEGRAM_BOT_TOKEN" ]] || [[ -z "$TELEGRAM_WEBHOOK_SECRET" ]]; then
  echo "ERROR: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_SECRET in $BACKEND_ENV" >&2
  exit 1
fi

# Start tunnelmole in background
echo "Starting tunnelmole for port 8000..."
tunnelmole 8000 > "$LOG_FILE" 2>&1 &
TM_PID=$!

# Wait for URL to appear in log
echo "Waiting for tunnelmole URL (max ${MAX_WAIT}s)..."
for i in $(seq 1 $MAX_WAIT); do
  if grep -qE 'https://.*\.tunnelmole\.net' "$LOG_FILE" 2>/dev/null; then
    break
  fi
  sleep 1
done

# Extract URL
TM_URL=$(grep -oE 'https://[a-zA-Z0-9-]+\.tunnelmole\.net' "$LOG_FILE" | head -1)

if [[ -z "$TM_URL" ]]; then
  echo "ERROR: Failed to extract tunnelmole URL from $LOG_FILE" >&2
  kill $TM_PID 2>/dev/null || true
  exit 1
fi

echo "Tunnelmole URL: $TM_URL"

# Register webhook with Telegram
WEBHOOK_URL="${TM_URL}/api/v1/telegram/webhook"
echo "Registering webhook: $WEBHOOK_URL"

RESPONSE=$(curl -s --max-time 15 -X POST "${TELEGRAM_API}/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -F "url=${WEBHOOK_URL}" \
  -F "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  -F "drop_pending_updates=true" \
  -F 'allowed_updates=["message","callback_query"]')

if echo "$RESPONSE" | grep -q '"ok":true'; then
  echo "SUCCESS: Webhook registered"
  echo "$RESPONSE"
else
  echo "ERROR: Failed to register webhook: $RESPONSE" >&2
  kill $TM_PID 2>/dev/null || true
  exit 1
fi

# Keep tunnelmole running in foreground (for systemd)
echo "Tunnelmole running (PID: $TM_PID)"
wait $TM_PID
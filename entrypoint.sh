#!/bin/bash
set -e

if id -u seluser >/dev/null 2>&1 && [ -d /home/seluser/files ]; then
  chown -R seluser:seluser /home/seluser/files
fi

SELENIUM_HOST="${SELENIUM_HOST:-localhost}"
SELENIUM_PORT="${SELENIUM_PORT:-4444}"
CONFIG_PATH="${CONFIG_PATH:-/data/blackbin_config.json}"
ENABLE_WEB_UI="${ENABLE_WEB_UI:-true}"
WEB_UI_HOST="${WEB_UI_HOST:-0.0.0.0}"
WEB_UI_PORT="${WEB_UI_PORT:-5050}"

DEFAULT_CRON_LINES=(
  "30 19 * * 1,5,6"
  "30 3 * * 3"
)

get_config_cron() {
  python - <<'PY'
import json
import os
path = os.getenv("CONFIG_PATH", "/data/blackbin_config.json")
try:
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    cron = config.get("schedule", {}).get("cron", [])
    if isinstance(cron, str):
        cron = [cron]
    for line in cron:
        line = str(line).strip()
        if line:
            print(line)
except FileNotFoundError:
    pass
except Exception:
    pass
PY
}

CRON_LINES=()
if [ -n "$CRON_SCHEDULES" ]; then
  IFS=';' read -r -a CRON_LINES <<< "$CRON_SCHEDULES"
elif [ -n "$CRON_SCHEDULE" ]; then
  CRON_LINES=("$CRON_SCHEDULE")
else
  CONFIG_CRON="$(get_config_cron)"
  if [ -n "$CONFIG_CRON" ]; then
    mapfile -t CRON_LINES <<< "$CONFIG_CRON"
  else
    CRON_LINES=("${DEFAULT_CRON_LINES[@]}")
  fi
fi

tmpfile="$(mktemp)"
for line in "${CRON_LINES[@]}"; do
  line="$(echo "$line" | xargs)"
  if [ -n "$line" ]; then
    echo "$line cd /app && /usr/local/bin/python /app/blackbin.py >/dev/null 2>&1" >> "$tmpfile"
  fi
done

crontab "$tmpfile"
rm -f "$tmpfile"

if [ "$ENABLE_WEB_UI" = "true" ]; then
  echo "Starting web UI on ${WEB_UI_HOST}:${WEB_UI_PORT}"
  python /app/web_ui.py --host "$WEB_UI_HOST" --port "$WEB_UI_PORT" &
fi

# Wait for Selenium to be available
echo "Waiting for selenium server at ${SELENIUM_HOST}:${SELENIUM_PORT}..."
until nc -z "$SELENIUM_HOST" "$SELENIUM_PORT"; do
  echo "selenium server not yet available, sleeping for 2 seconds..."
  sleep 2
done
echo "selenium server is available."

exec cron -f

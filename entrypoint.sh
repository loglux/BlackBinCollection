#!/bin/bash
chown -R seluser:seluser /home/seluser/files

SELENIUM_HOST="${SELENIUM_HOST:-localhost}"
SELENIUM_PORT="${SELENIUM_PORT:-4444}"

# Wait for Selenium to be available
echo "Waiting for selenium server at ${SELENIUM_HOST}:${SELENIUM_PORT}..."
until nc -z "$SELENIUM_HOST" "$SELENIUM_PORT"; do
  echo "selenium server not yet available, sleeping for 2 seconds..."
  sleep 2
done
echo "selenium server is available."

# Original CMD from Dockerfile is "cron -f"
exec cron -f

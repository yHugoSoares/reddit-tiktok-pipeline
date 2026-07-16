#!/bin/bash
# install_cron.sh — Install cron entries for 3 daily pipeline runs.
#
# Usage:
#   bash scripts/install_cron.sh
#
# Edit PROJECT_DIR below to point to your project directory.

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CRON_LOG="${PROJECT_DIR}/logs/cron.log"

CRON_ENTRIES="0 9 * * * cd ${PROJECT_DIR} && docker compose run --rm reddit-bot >> ${CRON_LOG} 2>&1
0 14 * * * cd ${PROJECT_DIR} && docker compose run --rm reddit-bot >> ${CRON_LOG} 2>&1
0 19 * * * cd ${PROJECT_DIR} && docker compose run --rm reddit-bot >> ${CRON_LOG} 2>&1"

# Remove any existing entries for this project
(crontab -l 2>/dev/null | grep -v "docker compose run --rm reddit-bot") | crontab - 2>/dev/null

# Add new entries
(crontab -l 2>/dev/null; echo "$CRON_ENTRIES") | crontab -

echo "Cron installed. Runs at 09:00, 14:00, 19:00 daily."
echo "Logs: ${CRON_LOG}"
echo ""
echo "To view: crontab -l"
echo "To remove: crontab -r"

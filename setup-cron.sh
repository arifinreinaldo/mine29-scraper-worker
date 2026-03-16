#!/bin/bash
set -euo pipefail

CRON_JOB="0 */6 * * * cd /opt/mine29-scraper-worker && python3 -m src.main >> /var/log/mine29.log 2>&1"
LOG_FILE="/var/log/mine29.log"

# Create log file
touch "$LOG_FILE"

# Add cron job if not already present
if crontab -l 2>/dev/null | grep -qF "mine29-scraper-worker"; then
    echo "Cron job already exists:"
    crontab -l | grep "mine29"
else
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Cron job added: runs every 6 hours"
fi

# Ensure cron service is running
systemctl enable --now cron 2>/dev/null || service cron start 2>/dev/null

echo "Done. Verify with: crontab -l"
echo "Logs at: $LOG_FILE"

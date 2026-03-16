#!/bin/sh
set -e

echo "Starting mine29-scraper-worker"
echo "Running initial scrape..."
cd /app && python -m src.main

echo "Starting cron..."
crond -f -l 2

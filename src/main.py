from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.config import load_config
from src.dedup import DedupStore
from src.models import AppConfig
from src.notifier import NtfyNotifier
from src.scraper import MCFScraper

logger = logging.getLogger("mine29")


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run(config: AppConfig) -> None:
    setup_logging(config.logging.level)
    logger.info("Starting mine29-scraper-worker")

    with (
        MCFScraper(config.scraper) as scraper,
        DedupStore(config.database.path) as dedup,
        NtfyNotifier(config.notifications) as notifier,
    ):
        for category in config.categories:
            logger.info("Processing category: %s", category.name)

            jobs = scraper.search(category)
            if not jobs:
                logger.info("No jobs found for %s", category.name)
                continue

            new_jobs = dedup.filter_new(jobs)
            logger.info(
                "%s: %d total, %d new", category.name, len(jobs), len(new_jobs)
            )

            dedup.mark_seen(new_jobs)

            if not new_jobs:
                continue

            visa_jobs = scraper.filter_visa_jobs(
                new_jobs, category.filters.visa_keywords
            )
            logger.info(
                "%s: %d visa-eligible jobs", category.name, len(visa_jobs)
            )

            if not visa_jobs:
                continue

            visa_jobs.sort(key=lambda j: j.posting_date, reverse=True)
            notified = notifier.notify(visa_jobs, category.ntfy_topic)
            dedup.mark_notified(notified)

            logger.info(
                "%s summary: %d fetched, %d new, %d visa-match, %d notified",
                category.name,
                len(jobs),
                len(new_jobs),
                len(visa_jobs),
                len(notified),
            )

        dedup.cleanup_old(config.database.retention_days)

    logger.info("Done")


def main() -> None:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    run(config)


if __name__ == "__main__":
    main()

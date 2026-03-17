from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from src.ai_filter import AIFilter
from src.config import load_config
from src.dedup import DedupStore
from src.keyword_filter import filter_visa_jobs
from src.models import AIConfig, AppConfig
from src.notifier import NtfyNotifier
from src.scraper import LinkedInScraper

logger = logging.getLogger("mine29")


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _enrich_with_ai(
    jobs: list, scraper: LinkedInScraper, ai: AIFilter, delay: float
) -> list:
    """Fetch descriptions and run AI enrichment. Falls back gracefully."""
    for i, job in enumerate(jobs):
        if not ai.is_available:
            logger.info("AI unavailable — remaining %d jobs pass through without AI", len(jobs) - i)
            break

        if i > 0:
            time.sleep(delay)

        job.description = scraper.fetch_description(job)
        if job.description:
            ai.enrich(job)

    return jobs


def run(config: AppConfig) -> None:
    setup_logging(config.logging.level)
    logger.info("Starting mine29-scraper-worker (LinkedIn)")

    ai_enabled = config.ai.enabled and config.ai.api_key
    ai: AIFilter | None = None

    with (
        LinkedInScraper(config.scraper) as scraper,
        DedupStore(config.database.path) as dedup,
        NtfyNotifier(config.notifications) as notifier,
    ):
        if ai_enabled:
            ai = AIFilter(config.ai)

        try:
            for category in config.categories:
                logger.info("Processing category: %s", category.name)

                jobs = scraper.search(category)
                if not jobs:
                    logger.info("No jobs found for %s", category.name)
                    continue

                # Layer 1: Keyword-based visa filter (always on, free)
                jobs = filter_visa_jobs(jobs)

                new_jobs = dedup.filter_new(jobs)
                logger.info(
                    "%s: %d total, %d new", category.name, len(jobs), len(new_jobs)
                )

                if not new_jobs:
                    continue

                dedup.mark_seen(new_jobs)

                # Layer 2: AI enrichment (best-effort, falls back to basic data)
                if ai and ai.is_available:
                    new_jobs = _enrich_with_ai(
                        new_jobs, scraper, ai, config.scraper.delay_between_requests
                    )

                new_jobs.sort(key=lambda j: j.posting_date, reverse=True)
                notified = notifier.notify(new_jobs, category.ntfy_topic, category)
                dedup.mark_notified(notified)

                logger.info(
                    "%s summary: %d fetched, %d new, %d notified",
                    category.name,
                    len(jobs),
                    len(new_jobs),
                    len(notified),
                )

            dedup.cleanup_old(config.database.retention_days)
        finally:
            if ai:
                ai.close()

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

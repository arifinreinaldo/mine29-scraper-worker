from __future__ import annotations

import logging
import sys
from pathlib import Path

from contextlib import ExitStack

from src.ai_filter import AIFilter
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

    with ExitStack() as stack:
        scraper = stack.enter_context(MCFScraper(config.scraper))
        dedup = stack.enter_context(DedupStore(config.database.path))
        notifier = stack.enter_context(NtfyNotifier(config.notifications))

        ai_filter: AIFilter | None = None
        if config.ai.enabled:
            ai_filter = stack.enter_context(AIFilter(config.ai))
            logger.info("AI visa filter enabled (model: %s)", config.ai.model)
        else:
            logger.info("AI disabled, using keyword-based visa filter")

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

            # Fetch descriptions for all new jobs (needed by both filters)
            jobs_with_desc = _fetch_descriptions(scraper, new_jobs)

            if ai_filter:
                visa_jobs = ai_filter.filter_visa_jobs(jobs_with_desc)
            else:
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


def _fetch_descriptions(scraper: MCFScraper, jobs: list) -> list:
    """Fetch full descriptions for jobs that don't have one yet."""
    import time

    result = []
    for i, job in enumerate(jobs):
        if not job.description:
            if i > 0:
                time.sleep(scraper._config.delay_between_requests)
            desc = scraper.fetch_job_details(job.uuid)
            if desc is not None:
                job.description = desc
                result.append(job)
            else:
                logger.warning("Could not fetch details for %s, skipping", job.uuid)
        else:
            result.append(job)
    return result


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

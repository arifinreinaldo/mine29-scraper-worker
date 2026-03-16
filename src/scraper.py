from __future__ import annotations

import html
import logging
import re
import time
from urllib.parse import quote_plus

import httpx

from src.models import CategoryConfig, Job, ScraperConfig

logger = logging.getLogger(__name__)

BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# LinkedIn experience level filter (f_E)
EXPERIENCE_LEVELS = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid-senior": "4",
    "director": "5",
    "executive": "6",
}

MAX_RETRIES = 3
RETRY_BASE_DELAY = 3.0


class LinkedInScraper:
    def __init__(self, config: ScraperConfig) -> None:
        self._config = config
        self._client = httpx.Client(
            timeout=config.request_timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    def search(self, category: CategoryConfig) -> list[Job]:
        all_jobs: list[Job] = []

        for page in range(self._config.max_pages):
            if page > 0:
                time.sleep(self._config.delay_between_requests)

            start = page * self._config.page_size
            url = self._build_url(category, start)
            html_content = self._get_with_retry(url)
            if html_content is None:
                logger.error("Failed to fetch page %d for %s", page, category.name)
                break

            jobs = self._parse_jobs(html_content, category.name)
            if not jobs:
                logger.debug("No more results on page %d for %s", page, category.name)
                break

            all_jobs.extend(jobs)

        logger.info("Fetched %d jobs for %s", len(all_jobs), category.name)
        return all_jobs

    def _build_url(self, category: CategoryConfig, start: int) -> str:
        params = {
            "keywords": quote_plus(category.keywords),
            "location": quote_plus(category.location),
            "f_SB2": "4",  # visa sponsorship
            "start": str(start),
            "sortBy": "DD",  # most recent
        }

        if category.experience_level:
            levels = [
                EXPERIENCE_LEVELS[lvl.strip().lower()]
                for lvl in category.experience_level.split(",")
                if lvl.strip().lower() in EXPERIENCE_LEVELS
            ]
            if levels:
                params["f_E"] = ",".join(levels)

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{BASE_URL}?{query}"

    def _parse_jobs(self, html_content: str, category: str) -> list[Job]:
        jobs: list[Job] = []

        card_pattern = re.compile(
            r'data-entity-urn="urn:li:jobPosting:(\d+)"', re.DOTALL
        )
        cards = html_content.split("</li>")

        for card in cards:
            id_match = card_pattern.search(card)
            if not id_match:
                continue

            job_id = id_match.group(1)
            title = self._extract(card, r'class="base-search-card__title[^"]*"[^>]*>(.*?)<')
            company = self._extract(
                card,
                r'class="base-search-card__subtitle[^"]*"[^>]*>\s*(?:<a[^>]*>)?(.*?)(?:</a>)?<',
            )
            location = self._extract(card, r'class="job-search-card__location[^"]*"[^>]*>(.*?)<')
            url = self._extract(card, r'<a[^>]*class="base-card__full-link[^"]*"[^>]*href="([^"]+)"')
            date = self._extract(card, r'<time[^>]*datetime="([^"]+)"')
            salary = self._extract(card, r'class="job-search-card__salary-info[^"]*"[^>]*>(.*?)<')

            if not title or not job_id:
                continue

            # Clean URL — remove tracking params
            if url:
                url = html.unescape(url).split("?")[0]

            jobs.append(
                Job(
                    uuid=job_id,
                    title=self._clean(title),
                    company=self._clean(company) or "Unknown",
                    category=category,
                    location=self._clean(location) or "Singapore",
                    posting_date=date or "",
                    url=url or f"https://www.linkedin.com/jobs/view/{job_id}",
                    salary=self._clean(salary),
                )
            )

        return jobs

    def _extract(self, text: str, pattern: str) -> str:
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1) if match else ""

    def _clean(self, text: str) -> str:
        text = html.unescape(text)
        text = re.sub(r"<[^>]+>", "", text)
        return text.strip()

    def _get_with_retry(self, url: str) -> str | None:
        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.get(url)
                if response.status_code == 429:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    logger.warning("Rate limited, retrying in %.1fs", delay)
                    time.sleep(delay)
                    continue
                if response.status_code >= 500:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    logger.warning("Server error %d, retrying in %.1fs", response.status_code, delay)
                    time.sleep(delay)
                    continue
                if response.status_code == 400 or response.status_code == 404:
                    logger.debug("No results (HTTP %d)", response.status_code)
                    return None
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as e:
                logger.error("HTTP error: %s", e)
                return None
            except httpx.RequestError as e:
                delay = RETRY_BASE_DELAY * (2**attempt)
                logger.warning("Request error: %s, retrying in %.1fs", e, delay)
                time.sleep(delay)
        logger.error("All retries exhausted for %s", url)
        return None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> LinkedInScraper:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

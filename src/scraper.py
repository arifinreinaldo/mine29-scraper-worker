from __future__ import annotations

import logging
import re
import time

import httpx

from src.models import CategoryConfig, Job, ScraperConfig

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0


class MCFScraper:
    def __init__(self, config: ScraperConfig) -> None:
        self._config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.request_timeout,
            headers={"Content-Type": "application/json"},
        )

    def search(self, category: CategoryConfig) -> list[Job]:
        all_jobs: list[Job] = []

        for page in range(self._config.max_pages):
            if page > 0:
                time.sleep(self._config.delay_between_requests)

            body = self._build_search_body(category, page)
            data = self._post_with_retry("/v2/search", body)
            if data is None:
                logger.error("Failed to fetch page %d for %s", page, category.name)
                break

            results = data.get("results", [])
            if not results:
                logger.debug("No more results on page %d for %s", page, category.name)
                break

            jobs = [self._parse_job(r, category.name) for r in results]
            jobs = [j for j in jobs if j is not None]
            all_jobs.extend(jobs)

            total = data.get("total", 0)
            fetched = (page + 1) * self._config.page_size
            if fetched >= total:
                break

        logger.info("Fetched %d jobs for %s", len(all_jobs), category.name)
        return all_jobs

    def fetch_job_details(self, uuid: str) -> str | None:
        data = self._get_with_retry(f"/v2/jobs/{uuid}")
        if data is None:
            return None
        return data.get("description", "") or ""

    def filter_visa_jobs(
        self,
        jobs: list[Job],
        visa_keywords: list[str],
    ) -> list[Job]:
        if not visa_keywords:
            return jobs

        patterns = [re.compile(re.escape(kw), re.IGNORECASE) for kw in visa_keywords]
        visa_jobs: list[Job] = []

        for i, job in enumerate(jobs):
            description = job.description
            if not description:
                if i > 0:
                    time.sleep(self._config.delay_between_requests)
                description = self.fetch_job_details(job.uuid)
                if description is None:
                    logger.warning("Could not fetch details for %s, skipping visa check", job.uuid)
                    continue
                job.description = description

            if any(p.search(description) for p in patterns):
                job.visa_matched = True
                visa_jobs.append(job)
                logger.debug("Visa keyword match: %s @ %s", job.title, job.company)

        logger.info(
            "Visa filter: %d/%d jobs matched keywords", len(visa_jobs), len(jobs)
        )
        return visa_jobs

    def _build_search_body(self, category: CategoryConfig, page: int) -> dict:
        body: dict = {
            "search": "",
            "limit": self._config.page_size,
            "page": page,
            "sortBy": [{"field": "new_posting_date", "order": "desc"}],
            "categories": [category.api_category],
        }

        filters = category.filters
        if filters.min_salary > 0:
            body["salary"] = {"min": filters.min_salary}
        if filters.employment_types:
            body["employmentTypes"] = filters.employment_types
        if filters.position_levels:
            body["positionLevels"] = filters.position_levels

        return body

    def _parse_job(self, result: dict, category: str) -> Job | None:
        try:
            metadata = result.get("_source", result)
            uuid = metadata.get("uuid", "")
            if not uuid:
                return None

            salary = metadata.get("salary", {}) or {}
            return Job(
                uuid=uuid,
                title=metadata.get("title", "Unknown"),
                company=metadata.get("postedCompany", {}).get("name", "Unknown"),
                category=category,
                min_salary=int(salary.get("minimum", 0) or 0),
                max_salary=int(salary.get("maximum", 0) or 0),
                position_level=metadata.get("positionLevel", ""),
                employment_type=metadata.get("employmentType", ""),
                posting_date=metadata.get("newPostingDate", ""),
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("Failed to parse job result: %s", e)
            return None

    def _post_with_retry(self, path: str, body: dict) -> dict | None:
        return self._request_with_retry("POST", path, json=body)

    def _get_with_retry(self, path: str) -> dict | None:
        return self._request_with_retry("GET", path)

    def _request_with_retry(self, method: str, path: str, **kwargs) -> dict | None:
        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.request(method, path, **kwargs)
                if response.status_code == 429:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    logger.warning("Rate limited, retrying in %.1fs", delay)
                    time.sleep(delay)
                    continue
                if response.status_code >= 500:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        "Server error %d, retrying in %.1fs", response.status_code, delay
                    )
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error("HTTP error: %s", e)
                return None
            except httpx.RequestError as e:
                delay = RETRY_BASE_DELAY * (2**attempt)
                logger.warning("Request error: %s, retrying in %.1fs", e, delay)
                time.sleep(delay)
        logger.error("All retries exhausted for %s %s", method, path)
        return None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> MCFScraper:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

from __future__ import annotations

import logging

import httpx

from src.models import AIConfig, Job

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a job listing analyst. Given a job description, determine if the employer \
is willing to hire foreign workers who need a work visa (Employment Pass, S Pass, etc.).

Reply with ONLY "yes" or "no".

Indicators of visa willingness:
- Mentions Employment Pass (EP), S Pass, work visa, visa sponsorship
- Says "foreigners welcome" or "open to all nationalities"
- Does NOT restrict to Singapore citizens/PRs only

Indicators of NO visa willingness:
- Explicitly requires Singapore citizenship or PR status
- Says "Singaporeans only" or "SC/PR only"
- No mention of visa/foreign workers (ambiguous = no)
"""


class AIFilter:
    def __init__(self, config: AIConfig) -> None:
        self._config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.request_timeout,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
        )

    def is_visa_eligible(self, job: Job) -> bool:
        if not job.description:
            return False

        truncated = job.description[:3000]

        user_msg = (
            f"Job Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Description:\n{truncated}\n\n"
            "Is this employer willing to hire foreign workers who need a work visa?"
        )

        body = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 10,
            "temperature": 0.0,
        }

        try:
            response = self._client.post("/chat/completions", json=body)
            response.raise_for_status()
            data = response.json()
            answer = data["choices"][0]["message"]["content"].strip().lower()
            result = answer.startswith("yes")
            logger.debug(
                "AI visa check for %s @ %s: %s (raw: %s)",
                job.title, job.company, result, answer,
            )
            return result
        except (httpx.HTTPError, KeyError, IndexError) as e:
            logger.error("AI filter failed for %s: %s", job.uuid, e)
            return False

    def filter_visa_jobs(self, jobs: list[Job]) -> list[Job]:
        visa_jobs: list[Job] = []
        for job in jobs:
            if self.is_visa_eligible(job):
                visa_jobs.append(job)

        logger.info("AI visa filter: %d/%d jobs matched", len(visa_jobs), len(jobs))
        return visa_jobs

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AIFilter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

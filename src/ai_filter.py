from __future__ import annotations

import json
import logging

import httpx

from src.models import AIConfig, Job

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a job listing analyst. Given a job description, analyze it and respond \
with a JSON object containing exactly these fields:

{
  "visa_sponsored": true or false,
  "urgency": "high" or "medium" or "low",
  "summary": "1-2 sentence summary of key requirements and what the role does"
}

Rules for visa_sponsored:
- true: mentions Employment Pass, S Pass, work visa, visa sponsorship, \
"foreigners welcome", "open to all nationalities", does NOT restrict to \
Singapore citizens/PRs only
- false: requires Singapore citizenship/PR, says "SC/PR only", \
"Singaporeans only", or no mention of visa (ambiguous = false)

Rules for urgency (how eager the employer is to hire):
- "high": signals like "immediate start", "urgent hiring", "ASAP", \
multiple openings, signing bonus, relocation support, "fast-track", \
"immediate need"
- "medium": standard posting, no special urgency or delay signals
- "low": future pipeline, "talent pool", no concrete start date, \
"expressions of interest"

Rules for summary:
- Concise 1-2 sentences covering: key skills needed, years of experience, \
and what the role does
- Focus on hard requirements, not nice-to-haves

Reply with ONLY the JSON object, no other text.\
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
        self._hit_limit = False

    def enrich(self, job: Job) -> bool:
        """Enrich a job with AI analysis. Returns True if AI data was added, False on failure."""
        if self._hit_limit:
            return False

        if not job.description:
            return False

        truncated = job.description[:3000]

        user_msg = (
            f"Job Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Description:\n{truncated}"
        )

        body = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 200,
            "temperature": 0.0,
        }

        try:
            response = self._client.post("/chat/completions", json=body)

            if response.status_code == 429:
                logger.warning("AI rate limited — falling back to normal scraping")
                self._hit_limit = True
                return False

            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            return self._parse_and_apply(content, job)

        except httpx.TimeoutException:
            logger.warning("AI request timed out for %s — skipping AI enrichment", job.uuid)
            return False
        except httpx.HTTPError as e:
            if _is_quota_error(e):
                logger.warning("AI quota exceeded — falling back to normal scraping")
                self._hit_limit = True
            else:
                logger.error("AI request failed for %s: %s", job.uuid, e)
            return False
        except (KeyError, IndexError) as e:
            logger.error("AI response parse error for %s: %s", job.uuid, e)
            return False

    def _parse_and_apply(self, content: str, job: Job) -> bool:
        """Parse JSON from AI response and apply fields to the job."""
        # Strip markdown code fences if present
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("AI returned non-JSON for %s: %s", job.uuid, content[:100])
            return False

        visa = result.get("visa_sponsored")
        urgency = result.get("urgency", "medium")
        summary = result.get("summary", "")

        if urgency not in ("high", "medium", "low"):
            urgency = "medium"

        job.urgency = urgency
        job.summary = summary[:300]  # cap length

        is_visa = bool(visa)
        logger.debug(
            "AI enriched %s @ %s: visa=%s urgency=%s",
            job.title, job.company, is_visa, urgency,
        )
        return is_visa

    def enrich_jobs(self, jobs: list[Job]) -> list[Job]:
        """Enrich jobs with AI analysis. Filters out non-visa-sponsored jobs.

        On AI failure, jobs pass through without filtering (fallback).
        """
        enriched: list[Job] = []
        skipped: list[Job] = []

        for job in jobs:
            is_visa = self.enrich(job)

            if self._hit_limit:
                # AI hit limit — let remaining jobs pass through unfiltered
                skipped.append(job)
                skipped.extend(jobs[jobs.index(job) + 1 :])
                break

            if is_visa:
                enriched.append(job)
            elif not job.description:
                # No description to analyze — pass through
                skipped.append(job)
            else:
                logger.debug("AI filtered out (no visa): %s @ %s", job.title, job.company)

        result = enriched + skipped
        logger.info(
            "AI enrichment: %d enriched, %d passed through, %d filtered out of %d",
            len(enriched), len(skipped), len(jobs) - len(result), len(jobs),
        )
        return result

    @property
    def is_available(self) -> bool:
        return not self._hit_limit

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AIFilter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _is_quota_error(error: httpx.HTTPError) -> bool:
    """Check if the error indicates API quota/billing exhaustion."""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in (402, 403, 429)
    return False

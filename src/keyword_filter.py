from __future__ import annotations

import logging
import re

from src.models import Job

logger = logging.getLogger(__name__)

# Patterns indicating the job does NOT sponsor visas.
# These are checked against title + company (case-insensitive).
_NO_VISA_PATTERNS = [
    r"\bsc[/ ]pr\s+only\b",
    r"\bsc[/ ]pr\b",
    r"\bsingaporeans?\s+only\b",
    r"\bcitizens?\s+only\b",
    r"\bpr\s+only\b",
    r"\bno\s+visa\b",
    r"\bvisa\s+not\s+sponsored\b",
    r"\bwithout\s+visa\b",
    r"\bno\s+sponsorship\b",
    r"\bno\s+work\s+pass\b",
    r"\bsingapore\s+citizen(?:s|ship)?\s+(?:only|required)\b",
    r"\bpermanent\s+resident(?:s)?\s+only\b",
]

_COMPILED = re.compile("|".join(_NO_VISA_PATTERNS), re.IGNORECASE)


def is_visa_excluded(job: Job) -> bool:
    """Return True if the job title signals no visa sponsorship."""
    text = f"{job.title} {job.company}"
    return bool(_COMPILED.search(text))


def filter_visa_jobs(jobs: list[Job]) -> list[Job]:
    """Remove jobs whose titles indicate no visa sponsorship."""
    kept: list[Job] = []
    removed = 0
    for job in jobs:
        if is_visa_excluded(job):
            logger.debug("Keyword filter removed: %s @ %s", job.title, job.company)
            removed += 1
        else:
            kept.append(job)

    if removed:
        logger.info("Keyword visa filter removed %d/%d jobs", removed, len(jobs))
    return kept

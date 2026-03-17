from __future__ import annotations

import logging
import re

import httpx

from src.models import CategoryConfig, Job, NotificationConfig

logger = logging.getLogger(__name__)


def _ascii_safe(text: str) -> str:
    return text.encode("ascii", errors="replace").decode("ascii")


def _matches_highlight(title: str, keywords: list[str]) -> bool:
    """Check if the job title matches any highlight keywords (case-insensitive)."""
    title_lower = title.lower()
    return any(re.search(rf"\b{re.escape(kw.lower())}\b", title_lower) for kw in keywords)


class NtfyNotifier:
    def __init__(self, config: NotificationConfig) -> None:
        self._config = config
        headers: dict[str, str] = {}
        if config.ntfy_token:
            headers["Authorization"] = f"Bearer {config.ntfy_token}"
        self._client = httpx.Client(timeout=15, headers=headers)

    def notify(
        self, jobs: list[Job], topic: str, category: CategoryConfig | None = None
    ) -> list[str]:
        batch = jobs[: self._config.batch_size]
        notified_uuids: list[str] = []

        highlight_keywords = category.highlight_keywords if category else []

        for job in batch:
            if self._send(job, topic, highlight_keywords):
                notified_uuids.append(job.uuid)

        logger.info(
            "Notified %d/%d jobs to topic %s",
            len(notified_uuids),
            len(batch),
            topic,
        )
        return notified_uuids

    def _send(self, job: Job, topic: str, highlight_keywords: list[str]) -> bool:
        url = f"{self._config.ntfy_server.rstrip('/')}/{topic}"

        # Build body lines
        lines = [f"{job.company} | {job.salary_display} | {job.location}"]
        if job.summary:
            lines.append(f"Needs: {job.summary}")

        body = "\n".join(lines)

        # Build tags
        tags = ["briefcase"]
        if job.is_high_need:
            tags.append("fire")
        if highlight_keywords and _matches_highlight(job.title, highlight_keywords):
            tags.append("star")

        # Build title with urgency prefix
        title_parts = []
        if job.is_high_need:
            title_parts.append("[HIGH NEED]")
        title_parts.append(job.title)
        title = _ascii_safe(" ".join(title_parts))

        # Priority: high for urgent jobs or highlighted matches
        priority = self._config.priority
        if job.is_high_need:
            priority = "high"
        elif highlight_keywords and _matches_highlight(job.title, highlight_keywords):
            priority = "high"

        headers = {
            "Title": title,
            "Tags": ",".join(tags),
            "Priority": priority,
            "Click": job.url,
        }

        try:
            response = self._client.post(url, content=body.encode("utf-8"), headers=headers)
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Failed to notify %s: %s", job.uuid, e)
            return False

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NtfyNotifier:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

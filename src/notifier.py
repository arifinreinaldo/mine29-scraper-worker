from __future__ import annotations

import logging

import httpx

from src.models import Job, NotificationConfig

logger = logging.getLogger(__name__)


def _ascii_safe(text: str) -> str:
    return text.encode("ascii", errors="replace").decode("ascii")


class NtfyNotifier:
    def __init__(self, config: NotificationConfig) -> None:
        self._config = config
        headers: dict[str, str] = {}
        if config.ntfy_token:
            headers["Authorization"] = f"Bearer {config.ntfy_token}"
        self._client = httpx.Client(timeout=15, headers=headers)

    def notify(self, jobs: list[Job], topic: str) -> list[str]:
        batch = jobs[: self._config.batch_size]
        notified_uuids: list[str] = []

        for job in batch:
            if self._send(job, topic):
                notified_uuids.append(job.uuid)

        logger.info(
            "Notified %d/%d jobs to topic %s",
            len(notified_uuids),
            len(batch),
            topic,
        )
        return notified_uuids

    def _send(self, job: Job, topic: str) -> bool:
        url = f"{self._config.ntfy_server.rstrip('/')}/{topic}"
        body = f"{job.company} | {job.salary_display} | {job.location}"
        title = _ascii_safe(job.title)
        headers = {
            "Title": title,
            "Tags": "briefcase",
            "Priority": self._config.priority,
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

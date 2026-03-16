import httpx
import pytest
import respx

from src.models import Job, NotificationConfig
from src.notifier import NtfyNotifier


def _make_job(uuid: str = "test-uuid", **kwargs) -> Job:
    defaults = dict(
        uuid=uuid,
        title="Software Engineer",
        company="Tech Corp",
        category="IT",
        min_salary=6000,
        max_salary=10000,
        position_level="Executive",
        employment_type="Full Time",
        posting_date="2026-03-15",
    )
    defaults.update(kwargs)
    return Job(**defaults)


def _make_config(**kwargs) -> NotificationConfig:
    defaults = dict(
        ntfy_server="https://ntfy.sh",
        ntfy_token="",
        priority="default",
        batch_size=10,
    )
    defaults.update(kwargs)
    return NotificationConfig(**defaults)


class TestNtfyNotifier:
    @respx.mock
    def test_notify_sends_correct_request(self):
        route = respx.post("https://ntfy.sh/test-topic").mock(
            return_value=httpx.Response(200)
        )

        job = _make_job()
        with NtfyNotifier(_make_config()) as notifier:
            result = notifier.notify([job], "test-topic")

        assert result == ["test-uuid"]
        assert route.call_count == 1

        request = route.calls[0].request
        assert request.headers["Title"] == "Software Engineer @ Tech Corp"
        assert request.headers["Tags"] == "briefcase"
        assert request.headers["Priority"] == "default"
        assert request.headers["Click"] == "https://www.mycareersfuture.gov.sg/job/test-uuid"
        assert b"Tech Corp" in request.content
        assert b"SGD 6,000" in request.content

    @respx.mock
    def test_notify_respects_batch_size(self):
        route = respx.post("https://ntfy.sh/topic").mock(
            return_value=httpx.Response(200)
        )

        jobs = [_make_job(f"job-{i}") for i in range(15)]
        config = _make_config(batch_size=5)

        with NtfyNotifier(config) as notifier:
            result = notifier.notify(jobs, "topic")

        assert len(result) == 5
        assert route.call_count == 5

    @respx.mock
    def test_notify_handles_failure(self):
        respx.post("https://ntfy.sh/topic").mock(
            return_value=httpx.Response(500)
        )

        job = _make_job()
        with NtfyNotifier(_make_config()) as notifier:
            result = notifier.notify([job], "topic")

        assert result == []

    @respx.mock
    def test_notify_partial_failure(self):
        route = respx.post("https://ntfy.sh/topic").mock(
            side_effect=[
                httpx.Response(200),
                httpx.Response(500),
                httpx.Response(200),
            ]
        )

        jobs = [_make_job(f"job-{i}") for i in range(3)]
        with NtfyNotifier(_make_config()) as notifier:
            result = notifier.notify(jobs, "topic")

        assert result == ["job-0", "job-2"]

    @respx.mock
    def test_notify_empty_list(self):
        with NtfyNotifier(_make_config()) as notifier:
            result = notifier.notify([], "topic")
        assert result == []

    @respx.mock
    def test_auth_token_included(self):
        route = respx.post("https://ntfy.sh/topic").mock(
            return_value=httpx.Response(200)
        )

        job = _make_job()
        config = _make_config(ntfy_token="tk_secret123")
        with NtfyNotifier(config) as notifier:
            notifier.notify([job], "topic")

        request = route.calls[0].request
        assert request.headers["Authorization"] == "Bearer tk_secret123"

    @respx.mock
    def test_no_auth_header_without_token(self):
        route = respx.post("https://ntfy.sh/topic").mock(
            return_value=httpx.Response(200)
        )

        job = _make_job()
        with NtfyNotifier(_make_config(ntfy_token="")) as notifier:
            notifier.notify([job], "topic")

        request = route.calls[0].request
        assert "Authorization" not in request.headers

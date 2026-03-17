import httpx
import pytest
import respx

from src.models import CategoryConfig, Job, NotificationConfig
from src.notifier import NtfyNotifier


def _make_job(uuid: str = "test-uuid", **kwargs) -> Job:
    defaults = dict(
        uuid=uuid,
        title="Software Engineer",
        company="Tech Corp",
        category="IT",
        location="Singapore",
        posting_date="2026-03-15",
        url="https://www.linkedin.com/jobs/view/test-uuid",
        salary="SGD 6,000 - 10,000/mo",
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


def _make_category(**kwargs) -> CategoryConfig:
    defaults = dict(
        name="IT",
        keywords="software engineer",
        ntfy_topic="test-topic",
        location="Singapore",
        highlight_keywords=[],
    )
    defaults.update(kwargs)
    return CategoryConfig(**defaults)


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
        assert request.headers["Title"] == "Software Engineer"
        assert "briefcase" in request.headers["Tags"]
        assert request.headers["Priority"] == "default"
        assert request.headers["Click"] == "https://www.linkedin.com/jobs/view/test-uuid"
        assert b"Tech Corp" in request.content
        assert b"Singapore" in request.content

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


class TestHighNeedNotification:
    @respx.mock
    def test_high_urgency_adds_fire_tag_and_high_priority(self):
        route = respx.post("https://ntfy.sh/topic").mock(
            return_value=httpx.Response(200)
        )

        job = _make_job(urgency="high", summary="Needs Python, 3yr exp.")
        with NtfyNotifier(_make_config()) as notifier:
            notifier.notify([job], "topic")

        request = route.calls[0].request
        assert "fire" in request.headers["Tags"]
        assert "[HIGH NEED]" in request.headers["Title"]
        assert request.headers["Priority"] == "high"
        assert b"Needs: Needs Python, 3yr exp." in request.content

    @respx.mock
    def test_medium_urgency_normal_notification(self):
        route = respx.post("https://ntfy.sh/topic").mock(
            return_value=httpx.Response(200)
        )

        job = _make_job(urgency="medium", summary="SQL and Tableau required.")
        with NtfyNotifier(_make_config()) as notifier:
            notifier.notify([job], "topic")

        request = route.calls[0].request
        assert "fire" not in request.headers["Tags"]
        assert "[HIGH NEED]" not in request.headers["Title"]
        assert request.headers["Priority"] == "default"
        assert b"Needs: SQL and Tableau required." in request.content

    @respx.mock
    def test_no_summary_omits_needs_line(self):
        route = respx.post("https://ntfy.sh/topic").mock(
            return_value=httpx.Response(200)
        )

        job = _make_job()  # no urgency, no summary (fallback mode)
        with NtfyNotifier(_make_config()) as notifier:
            notifier.notify([job], "topic")

        request = route.calls[0].request
        assert b"Needs:" not in request.content


class TestHighlightKeywords:
    @respx.mock
    def test_graduate_marketing_gets_star_and_high_priority(self):
        route = respx.post("https://ntfy.sh/topic").mock(
            return_value=httpx.Response(200)
        )

        job = _make_job(title="Marketing Graduate Program")
        category = _make_category(
            name="Marketing",
            highlight_keywords=["graduate", "fresh grad", "junior"],
        )

        with NtfyNotifier(_make_config()) as notifier:
            notifier.notify([job], "topic", category)

        request = route.calls[0].request
        assert "star" in request.headers["Tags"]
        assert request.headers["Priority"] == "high"

    @respx.mock
    def test_non_matching_title_normal_priority(self):
        route = respx.post("https://ntfy.sh/topic").mock(
            return_value=httpx.Response(200)
        )

        job = _make_job(title="Senior Marketing Manager")
        category = _make_category(
            name="Marketing",
            highlight_keywords=["graduate", "fresh grad", "junior"],
        )

        with NtfyNotifier(_make_config()) as notifier:
            notifier.notify([job], "topic", category)

        request = route.calls[0].request
        assert "star" not in request.headers["Tags"]
        assert request.headers["Priority"] == "default"

    @respx.mock
    def test_no_category_no_highlight(self):
        route = respx.post("https://ntfy.sh/topic").mock(
            return_value=httpx.Response(200)
        )

        job = _make_job(title="Graduate Developer")
        with NtfyNotifier(_make_config()) as notifier:
            notifier.notify([job], "topic")  # no category passed

        request = route.calls[0].request
        assert "star" not in request.headers["Tags"]

    @respx.mock
    def test_high_need_plus_highlight_both_apply(self):
        route = respx.post("https://ntfy.sh/topic").mock(
            return_value=httpx.Response(200)
        )

        job = _make_job(title="Junior Marketing Exec", urgency="high", summary="Entry role")
        category = _make_category(highlight_keywords=["junior"])

        with NtfyNotifier(_make_config()) as notifier:
            notifier.notify([job], "topic", category)

        request = route.calls[0].request
        assert "fire" in request.headers["Tags"]
        assert "star" in request.headers["Tags"]
        assert "[HIGH NEED]" in request.headers["Title"]
        assert request.headers["Priority"] == "high"

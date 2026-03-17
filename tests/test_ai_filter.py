import json

import httpx
import pytest
import respx

from src.ai_filter import AIFilter
from src.models import AIConfig, Job

BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _make_config(**kwargs) -> AIConfig:
    defaults = dict(
        enabled=True,
        api_key="test-key",
        base_url=BASE_URL,
        model="qwen-plus",
        request_timeout=10,
    )
    defaults.update(kwargs)
    return AIConfig(**defaults)


def _make_job(uuid: str = "test-uuid", description: str = "", **kwargs) -> Job:
    defaults = dict(
        uuid=uuid,
        title="Software Engineer",
        company="Tech Corp",
        category="IT",
        location="Singapore",
        posting_date="2026-03-15",
        url="https://www.linkedin.com/jobs/view/test-uuid",
    )
    defaults.update(kwargs)
    job = Job(**defaults)
    job.description = description
    return job


def _mock_ai_response(visa: bool, urgency: str = "medium", summary: str = "Test summary") -> dict:
    content = json.dumps({
        "visa_sponsored": visa,
        "urgency": urgency,
        "summary": summary,
    })
    return {
        "choices": [{"message": {"content": content}}]
    }


class TestAIEnrich:
    @respx.mock
    def test_enriches_visa_eligible_job(self):
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json=_mock_ai_response(
                visa=True, urgency="high", summary="Needs 3yr Python, AWS."
            ))
        )

        job = _make_job(description="EP holders welcome. Immediate start.")
        with AIFilter(_make_config()) as f:
            result = f.enrich(job)

        assert result is True
        assert job.urgency == "high"
        assert job.summary == "Needs 3yr Python, AWS."

    @respx.mock
    def test_enriches_no_visa_job(self):
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json=_mock_ai_response(visa=False))
        )

        job = _make_job(description="SC/PR only.")
        with AIFilter(_make_config()) as f:
            result = f.enrich(job)

        assert result is False
        assert job.urgency == "medium"

    @respx.mock
    def test_empty_description_returns_false(self):
        job = _make_job(description="")
        with AIFilter(_make_config()) as f:
            assert f.enrich(job) is False

    @respx.mock
    def test_api_error_returns_false(self):
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(500)
        )

        job = _make_job(description="Some description")
        with AIFilter(_make_config()) as f:
            assert f.enrich(job) is False

    @respx.mock
    def test_rate_limit_sets_hit_limit(self):
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(429)
        )

        job = _make_job(description="Some description")
        with AIFilter(_make_config()) as f:
            assert f.enrich(job) is False
            assert f.is_available is False
            # Subsequent calls immediately return False
            assert f.enrich(_make_job(description="Another")) is False

    @respx.mock
    def test_quota_exceeded_sets_hit_limit(self):
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(402)
        )

        job = _make_job(description="Some description")
        with AIFilter(_make_config()) as f:
            assert f.enrich(job) is False
            assert f.is_available is False

    @respx.mock
    def test_markdown_code_fence_stripped(self):
        content = '```json\n{"visa_sponsored": true, "urgency": "low", "summary": "Basic role"}\n```'
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": content}}]
            })
        )

        job = _make_job(description="Some job")
        with AIFilter(_make_config()) as f:
            result = f.enrich(job)

        assert result is True
        assert job.urgency == "low"
        assert job.summary == "Basic role"

    @respx.mock
    def test_invalid_json_returns_false(self):
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "not json at all"}}]
            })
        )

        job = _make_job(description="Some job")
        with AIFilter(_make_config()) as f:
            assert f.enrich(job) is False

    @respx.mock
    def test_invalid_urgency_defaults_to_medium(self):
        content = json.dumps({
            "visa_sponsored": True,
            "urgency": "super-urgent",
            "summary": "Something",
        })
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": content}}]
            })
        )

        job = _make_job(description="Job desc")
        with AIFilter(_make_config()) as f:
            f.enrich(job)
        assert job.urgency == "medium"


class TestEnrichJobs:
    @respx.mock
    def test_filters_non_visa_keeps_visa(self):
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            side_effect=[
                httpx.Response(200, json=_mock_ai_response(True, "high", "Python dev")),
                httpx.Response(200, json=_mock_ai_response(False)),
                httpx.Response(200, json=_mock_ai_response(True, "low", "Analyst role")),
            ]
        )

        jobs = [
            _make_job("j1", description="EP holders welcome"),
            _make_job("j2", description="SC/PR only"),
            _make_job("j3", description="Foreigners can apply"),
        ]

        with AIFilter(_make_config()) as f:
            result = f.enrich_jobs(jobs)

        assert len(result) == 2
        assert result[0].uuid == "j1"
        assert result[0].urgency == "high"
        assert result[1].uuid == "j3"
        assert route.call_count == 3

    @respx.mock
    def test_rate_limit_lets_remaining_pass_through(self):
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            side_effect=[
                httpx.Response(200, json=_mock_ai_response(True, "medium", "First")),
                httpx.Response(429),  # rate limited on second job
            ]
        )

        jobs = [
            _make_job("j1", description="Job 1"),
            _make_job("j2", description="Job 2"),
            _make_job("j3", description="Job 3"),
        ]

        with AIFilter(_make_config()) as f:
            result = f.enrich_jobs(jobs)

        # j1 enriched + passed, j2 failed + passed through, j3 passed through
        assert len(result) == 3
        assert result[0].uuid == "j1"
        assert result[0].urgency == "medium"
        # j2 and j3 have no AI data (fallback)
        assert result[1].uuid == "j2"
        assert result[1].urgency == ""
        assert result[2].uuid == "j3"

    @respx.mock
    def test_no_description_passes_through(self):
        jobs = [
            _make_job("j1", description=""),
            _make_job("j2", description=""),
        ]

        with AIFilter(_make_config()) as f:
            result = f.enrich_jobs(jobs)

        assert len(result) == 2

    @respx.mock
    def test_sends_correct_model_and_headers(self):
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json=_mock_ai_response(True))
        )

        job = _make_job(description="Test")
        with AIFilter(_make_config(api_key="sk-mykey", model="qwen-turbo")) as f:
            f.enrich(job)

        request = route.calls[0].request
        assert request.headers["Authorization"] == "Bearer sk-mykey"
        body = json.loads(request.content)
        assert body["model"] == "qwen-turbo"
        assert body["max_tokens"] == 200

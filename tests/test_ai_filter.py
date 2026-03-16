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


def _mock_qwen_response(answer: str) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": answer,
                }
            }
        ]
    }


class TestAIFilter:
    @respx.mock
    def test_visa_eligible_returns_true(self):
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json=_mock_qwen_response("yes"))
        )

        job = _make_job(description="We welcome Employment Pass holders to apply.")
        with AIFilter(_make_config()) as f:
            assert f.is_visa_eligible(job) is True

    @respx.mock
    def test_not_visa_eligible_returns_false(self):
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json=_mock_qwen_response("no"))
        )

        job = _make_job(description="Singaporeans only.")
        with AIFilter(_make_config()) as f:
            assert f.is_visa_eligible(job) is False

    @respx.mock
    def test_empty_description_returns_false(self):
        job = _make_job(description="")
        with AIFilter(_make_config()) as f:
            assert f.is_visa_eligible(job) is False

    @respx.mock
    def test_api_error_returns_false(self):
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(500)
        )

        job = _make_job(description="Some description")
        with AIFilter(_make_config()) as f:
            assert f.is_visa_eligible(job) is False

    @respx.mock
    def test_filter_visa_jobs_filters_correctly(self):
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            side_effect=[
                httpx.Response(200, json=_mock_qwen_response("yes")),
                httpx.Response(200, json=_mock_qwen_response("no")),
                httpx.Response(200, json=_mock_qwen_response("yes")),
            ]
        )

        jobs = [
            _make_job("j1", description="EP holders welcome"),
            _make_job("j2", description="SC/PR only"),
            _make_job("j3", description="Foreigners can apply"),
        ]

        with AIFilter(_make_config()) as f:
            result = f.filter_visa_jobs(jobs)

        assert len(result) == 2
        assert result[0].uuid == "j1"
        assert result[1].uuid == "j3"
        assert route.call_count == 3

    @respx.mock
    def test_sends_correct_headers(self):
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json=_mock_qwen_response("no"))
        )

        job = _make_job(description="Test")
        with AIFilter(_make_config(api_key="sk-mykey")) as f:
            f.is_visa_eligible(job)

        request = route.calls[0].request
        assert request.headers["Authorization"] == "Bearer sk-mykey"

    @respx.mock
    def test_sends_correct_model(self):
        route = respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json=_mock_qwen_response("no"))
        )

        job = _make_job(description="Test")
        with AIFilter(_make_config(model="qwen-turbo")) as f:
            f.is_visa_eligible(job)

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["model"] == "qwen-turbo"

    @respx.mock
    def test_case_insensitive_yes(self):
        respx.post(f"{BASE_URL}/chat/completions").mock(
            return_value=httpx.Response(200, json=_mock_qwen_response("Yes"))
        )

        job = _make_job(description="EP welcome")
        with AIFilter(_make_config()) as f:
            assert f.is_visa_eligible(job) is True

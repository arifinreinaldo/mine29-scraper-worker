from pathlib import Path

import httpx
import pytest
import respx

from src.config import load_config
from src.main import run

FIXTURES = Path(__file__).parent / "fixtures"


def _write_config(tmp_path, db_path, ai_enabled=False):
    config_content = f"""\
scraper:
  page_size: 25
  max_pages: 1
  request_timeout: 10
  delay_between_requests: 0

categories:
  - name: "IT"
    keywords: "software engineer"
    ntfy_topic: "test-it"
    location: "Singapore"
    highlight_keywords: []

notifications:
  ntfy_server: "https://ntfy.sh"
  batch_size: 10

database:
  path: "{db_path}"
  retention_days: 90

ai:
  enabled: {str(ai_enabled).lower()}
  api_key: "test-key"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  model: "qwen-plus"

logging:
  level: "DEBUG"
"""
    p = tmp_path / "config.yaml"
    p.write_text(config_content)
    return p


class TestIntegration:
    @respx.mock
    def test_full_pipeline(self, tmp_path):
        db_path = str(tmp_path / "test.db").replace("\\", "/")
        config_path = _write_config(tmp_path, db_path)
        config = load_config(config_path)

        fixture = (FIXTURES / "search_response.html").read_text()

        respx.get(url__startswith="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search").mock(
            return_value=httpx.Response(200, text=fixture)
        )
        ntfy_route = respx.post("https://ntfy.sh/test-it").mock(
            return_value=httpx.Response(200)
        )

        run(config)

        assert ntfy_route.call_count == 2
        request = ntfy_route.calls[0].request
        assert request.headers["Title"] == "Software Engineer"

    @respx.mock
    def test_dedup_prevents_duplicate_notifications(self, tmp_path):
        db_path = str(tmp_path / "test.db").replace("\\", "/")
        config_path = _write_config(tmp_path, db_path)
        config = load_config(config_path)

        fixture = (FIXTURES / "search_response.html").read_text()

        respx.get(url__startswith="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search").mock(
            return_value=httpx.Response(200, text=fixture)
        )
        ntfy_route = respx.post("https://ntfy.sh/test-it").mock(
            return_value=httpx.Response(200)
        )

        run(config)
        run(config)

        assert ntfy_route.call_count == 2  # only first run

    @respx.mock
    def test_no_jobs_found(self, tmp_path):
        db_path = str(tmp_path / "test.db").replace("\\", "/")
        config_path = _write_config(tmp_path, db_path)
        config = load_config(config_path)

        respx.get(url__startswith="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search").mock(
            return_value=httpx.Response(200, text="<html></html>")
        )

        run(config)

    @respx.mock
    def test_keyword_filter_removes_no_visa_jobs(self, tmp_path):
        """Jobs with 'SC/PR only' in title are filtered out before notification."""
        db_path = str(tmp_path / "test.db").replace("\\", "/")
        config_path = _write_config(tmp_path, db_path)
        config = load_config(config_path)

        # Inject a "SC/PR only" job into the fixture HTML
        html = """
        <li>
            <div data-entity-urn="urn:li:jobPosting:111">
                <a class="base-card__full-link" href="https://linkedin.com/jobs/view/111">link</a>
                <span class="base-search-card__title">Software Engineer</span>
                <span class="base-search-card__subtitle">Good Corp</span>
                <span class="job-search-card__location">Singapore</span>
                <time datetime="2026-03-15">Mar 15</time>
            </div>
        </li>
        <li>
            <div data-entity-urn="urn:li:jobPosting:222">
                <a class="base-card__full-link" href="https://linkedin.com/jobs/view/222">link</a>
                <span class="base-search-card__title">Developer (SC/PR Only)</span>
                <span class="base-search-card__subtitle">Restricted Corp</span>
                <span class="job-search-card__location">Singapore</span>
                <time datetime="2026-03-15">Mar 15</time>
            </div>
        </li>
        """

        respx.get(url__startswith="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search").mock(
            return_value=httpx.Response(200, text=html)
        )
        ntfy_route = respx.post("https://ntfy.sh/test-it").mock(
            return_value=httpx.Response(200)
        )

        run(config)

        # Only the first job should be notified (SC/PR one filtered)
        assert ntfy_route.call_count == 1
        request = ntfy_route.calls[0].request
        assert request.headers["Title"] == "Software Engineer"

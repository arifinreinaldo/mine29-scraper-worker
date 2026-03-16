from pathlib import Path

import httpx
import pytest
import respx

from src.config import load_config
from src.main import run

FIXTURES = Path(__file__).parent / "fixtures"


def _write_config(tmp_path, db_path):
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

notifications:
  ntfy_server: "https://ntfy.sh"
  batch_size: 10

database:
  path: "{db_path}"
  retention_days: 90

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

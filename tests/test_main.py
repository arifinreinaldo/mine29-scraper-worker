import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from src.config import load_config
from src.main import run

FIXTURES = Path(__file__).parent / "fixtures"


def _write_config(tmp_path, db_path):
    config_content = f"""\
scraper:
  base_url: "https://api.mycareersfuture.gov.sg"
  page_size: 100
  max_pages: 1
  request_timeout: 10
  delay_between_requests: 0

categories:
  - name: "IT"
    api_category: "Information Technology"
    ntfy_topic: "test-it"
    filters:
      employment_types: ["Full Time"]
      min_salary: 5000
      visa_keywords: ["Employment Pass", "EP"]

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

        search_fixture = json.loads(
            (FIXTURES / "search_response.json").read_text()
        )
        visa_detail = json.loads(
            (FIXTURES / "job_detail_visa.json").read_text()
        )
        no_visa_detail = json.loads(
            (FIXTURES / "job_detail_no_visa.json").read_text()
        )

        respx.post("https://api.mycareersfuture.gov.sg/v2/search").mock(
            return_value=httpx.Response(200, json=search_fixture)
        )
        respx.get("https://api.mycareersfuture.gov.sg/v2/jobs/abc-123").mock(
            return_value=httpx.Response(200, json=visa_detail)
        )
        respx.get("https://api.mycareersfuture.gov.sg/v2/jobs/def-456").mock(
            return_value=httpx.Response(200, json=no_visa_detail)
        )
        ntfy_route = respx.post("https://ntfy.sh/test-it").mock(
            return_value=httpx.Response(200)
        )

        run(config)

        assert ntfy_route.call_count == 1
        request = ntfy_route.calls[0].request
        assert request.headers["Title"] == "Software Engineer @ Tech Corp"

    @respx.mock
    def test_dedup_prevents_duplicate_notifications(self, tmp_path):
        db_path = str(tmp_path / "test.db").replace("\\", "/")
        config_path = _write_config(tmp_path, db_path)
        config = load_config(config_path)

        search_fixture = json.loads(
            (FIXTURES / "search_response.json").read_text()
        )
        visa_detail = json.loads(
            (FIXTURES / "job_detail_visa.json").read_text()
        )
        no_visa_detail = json.loads(
            (FIXTURES / "job_detail_no_visa.json").read_text()
        )

        respx.post("https://api.mycareersfuture.gov.sg/v2/search").mock(
            return_value=httpx.Response(200, json=search_fixture)
        )
        respx.get("https://api.mycareersfuture.gov.sg/v2/jobs/abc-123").mock(
            return_value=httpx.Response(200, json=visa_detail)
        )
        respx.get("https://api.mycareersfuture.gov.sg/v2/jobs/def-456").mock(
            return_value=httpx.Response(200, json=no_visa_detail)
        )
        ntfy_route = respx.post("https://ntfy.sh/test-it").mock(
            return_value=httpx.Response(200)
        )

        run(config)
        run(config)

        assert ntfy_route.call_count == 1

    @respx.mock
    def test_no_jobs_found(self, tmp_path):
        db_path = str(tmp_path / "test.db").replace("\\", "/")
        config_path = _write_config(tmp_path, db_path)
        config = load_config(config_path)

        respx.post("https://api.mycareersfuture.gov.sg/v2/search").mock(
            return_value=httpx.Response(200, json={"total": 0, "results": []})
        )

        run(config)

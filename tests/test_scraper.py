import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from src.models import CategoryConfig, FilterConfig, ScraperConfig
from src.scraper import MCFScraper

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _make_category(**kwargs) -> CategoryConfig:
    defaults = dict(
        name="IT",
        api_category="Information Technology",
        ntfy_topic="test-topic",
        filters=FilterConfig(min_salary=5000),
    )
    defaults.update(kwargs)
    return CategoryConfig(**defaults)


def _make_config(**kwargs) -> ScraperConfig:
    defaults = dict(
        base_url="https://api.mycareersfuture.gov.sg",
        page_size=100,
        max_pages=5,
        request_timeout=10,
        delay_between_requests=0,
    )
    defaults.update(kwargs)
    return ScraperConfig(**defaults)


class TestMCFScraperSearch:
    @respx.mock
    def test_search_parses_jobs(self):
        fixture = _load_fixture("search_response.json")
        respx.post("https://api.mycareersfuture.gov.sg/v2/search").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        with MCFScraper(_make_config()) as scraper:
            jobs = scraper.search(_make_category())

        assert len(jobs) == 2
        assert jobs[0].uuid == "abc-123"
        assert jobs[0].title == "Software Engineer"
        assert jobs[0].company == "Tech Corp"
        assert jobs[0].min_salary == 6000
        assert jobs[0].max_salary == 10000
        assert jobs[1].uuid == "def-456"

    @respx.mock
    def test_search_empty_results(self):
        respx.post("https://api.mycareersfuture.gov.sg/v2/search").mock(
            return_value=httpx.Response(200, json={"total": 0, "results": []})
        )

        with MCFScraper(_make_config()) as scraper:
            jobs = scraper.search(_make_category())

        assert jobs == []

    @respx.mock
    def test_search_stops_at_total(self):
        fixture = _load_fixture("search_response.json")
        fixture["total"] = 2

        route = respx.post("https://api.mycareersfuture.gov.sg/v2/search").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        with MCFScraper(_make_config(page_size=100)) as scraper:
            scraper.search(_make_category())

        assert route.call_count == 1

    @respx.mock
    def test_search_paginates(self):
        page0 = {
            "total": 150,
            "results": [
                {"_source": {"uuid": f"job-{i}", "title": "J", "postedCompany": {"name": "C"}, "salary": {"minimum": 6000, "maximum": 8000}, "positionLevel": "Exec", "employmentType": "Full Time", "newPostingDate": "2026-03-15"}}
                for i in range(100)
            ],
        }
        page1 = {
            "total": 150,
            "results": [
                {"_source": {"uuid": f"job-{i}", "title": "J", "postedCompany": {"name": "C"}, "salary": {"minimum": 6000, "maximum": 8000}, "positionLevel": "Exec", "employmentType": "Full Time", "newPostingDate": "2026-03-15"}}
                for i in range(100, 150)
            ],
        }

        route = respx.post("https://api.mycareersfuture.gov.sg/v2/search").mock(
            side_effect=[
                httpx.Response(200, json=page0),
                httpx.Response(200, json=page1),
            ]
        )

        with MCFScraper(_make_config()) as scraper:
            jobs = scraper.search(_make_category())

        assert len(jobs) == 150
        assert route.call_count == 2

    @respx.mock
    def test_search_handles_server_error(self):
        respx.post("https://api.mycareersfuture.gov.sg/v2/search").mock(
            return_value=httpx.Response(500)
        )

        with MCFScraper(_make_config()) as scraper:
            jobs = scraper.search(_make_category())

        assert jobs == []

    @respx.mock
    def test_search_body_includes_filters(self):
        respx.post("https://api.mycareersfuture.gov.sg/v2/search").mock(
            return_value=httpx.Response(200, json={"total": 0, "results": []})
        )

        category = _make_category(
            filters=FilterConfig(
                employment_types=["Full Time", "Part Time"],
                position_levels=["Executive", "Manager"],
                min_salary=7000,
            )
        )

        with MCFScraper(_make_config()) as scraper:
            scraper.search(category)

        request = respx.calls[0].request
        body = json.loads(request.content)
        assert body["salary"] == {"min": 7000}
        assert body["employmentTypes"] == ["Full Time", "Part Time"]
        assert body["positionLevels"] == ["Executive", "Manager"]
        assert body["categories"] == ["Information Technology"]
        assert body["sortBy"] == [{"field": "new_posting_date", "order": "desc"}]


class TestMCFScraperVisaFilter:
    @respx.mock
    def test_filter_visa_jobs_matches_keywords(self):
        visa_detail = _load_fixture("job_detail_visa.json")
        no_visa_detail = _load_fixture("job_detail_no_visa.json")

        respx.get("https://api.mycareersfuture.gov.sg/v2/jobs/abc-123").mock(
            return_value=httpx.Response(200, json=visa_detail)
        )
        respx.get("https://api.mycareersfuture.gov.sg/v2/jobs/def-456").mock(
            return_value=httpx.Response(200, json=no_visa_detail)
        )

        from src.models import Job

        jobs = [
            Job(uuid="abc-123", title="SE", company="TC", category="IT",
                min_salary=6000, max_salary=10000, position_level="Exec",
                employment_type="FT", posting_date="2026-03-15"),
            Job(uuid="def-456", title="MM", company="AA", category="IT",
                min_salary=7000, max_salary=12000, position_level="Mgr",
                employment_type="FT", posting_date="2026-03-14"),
        ]

        with MCFScraper(_make_config()) as scraper:
            visa_jobs = scraper.filter_visa_jobs(jobs, ["Employment Pass", "EP", "visa sponsorship"])

        assert len(visa_jobs) == 1
        assert visa_jobs[0].uuid == "abc-123"
        assert visa_jobs[0].visa_matched is True

    @respx.mock
    def test_filter_visa_jobs_empty_keywords_returns_all(self):
        from src.models import Job

        jobs = [
            Job(uuid="x", title="T", company="C", category="IT",
                min_salary=6000, max_salary=8000, position_level="E",
                employment_type="FT", posting_date="2026-03-15"),
        ]

        with MCFScraper(_make_config()) as scraper:
            result = scraper.filter_visa_jobs(jobs, [])

        assert len(result) == 1

    @respx.mock
    def test_filter_visa_jobs_handles_failed_detail_fetch(self):
        respx.get("https://api.mycareersfuture.gov.sg/v2/jobs/fail-1").mock(
            return_value=httpx.Response(500)
        )

        from src.models import Job

        jobs = [
            Job(uuid="fail-1", title="T", company="C", category="IT",
                min_salary=6000, max_salary=8000, position_level="E",
                employment_type="FT", posting_date="2026-03-15"),
        ]

        with MCFScraper(_make_config()) as scraper:
            result = scraper.filter_visa_jobs(jobs, ["EP"])

        assert result == []

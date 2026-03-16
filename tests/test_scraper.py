from pathlib import Path

import httpx
import pytest
import respx

from src.models import CategoryConfig, ScraperConfig
from src.scraper import LinkedInScraper

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _make_category(**kwargs) -> CategoryConfig:
    defaults = dict(
        name="IT",
        keywords="software engineer",
        ntfy_topic="test-topic",
        location="Singapore",
        experience_level="",
    )
    defaults.update(kwargs)
    return CategoryConfig(**defaults)


def _make_config(**kwargs) -> ScraperConfig:
    defaults = dict(
        page_size=25,
        max_pages=1,
        request_timeout=10,
        delay_between_requests=0,
    )
    defaults.update(kwargs)
    return ScraperConfig(**defaults)


class TestLinkedInScraperSearch:
    @respx.mock
    def test_search_parses_jobs(self):
        fixture = _load_fixture("search_response.html")
        respx.get(url__startswith="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search").mock(
            return_value=httpx.Response(200, text=fixture)
        )

        with LinkedInScraper(_make_config()) as scraper:
            jobs = scraper.search(_make_category())

        assert len(jobs) == 2
        assert jobs[0].uuid == "111111"
        assert jobs[0].title == "Software Engineer"
        assert jobs[0].company == "Tech Corp"
        assert jobs[0].location == "Singapore"
        assert jobs[0].posting_date == "2026-03-15"
        assert "111111" in jobs[0].url
        assert jobs[0].salary == "SGD 6,000 - 10,000/mo"

        assert jobs[1].uuid == "222222"
        assert jobs[1].company == "Ad Agency Pte Ltd"
        assert jobs[1].salary == ""

    @respx.mock
    def test_search_empty_results(self):
        respx.get(url__startswith="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search").mock(
            return_value=httpx.Response(200, text="<html></html>")
        )

        with LinkedInScraper(_make_config()) as scraper:
            jobs = scraper.search(_make_category())

        assert jobs == []

    @respx.mock
    def test_search_paginates(self):
        fixture = _load_fixture("search_response.html")

        respx.get(url__startswith="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search").mock(
            side_effect=[
                httpx.Response(200, text=fixture),
                httpx.Response(200, text=fixture),
                httpx.Response(200, text=""),
            ]
        )

        with LinkedInScraper(_make_config(max_pages=3)) as scraper:
            jobs = scraper.search(_make_category())

        assert len(jobs) == 4

    @respx.mock
    def test_search_handles_server_error(self):
        respx.get(url__startswith="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search").mock(
            return_value=httpx.Response(500)
        )

        with LinkedInScraper(_make_config()) as scraper:
            jobs = scraper.search(_make_category())

        assert jobs == []

    @respx.mock
    def test_url_includes_visa_filter(self):
        respx.get(url__startswith="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search").mock(
            return_value=httpx.Response(200, text="")
        )

        with LinkedInScraper(_make_config()) as scraper:
            scraper.search(_make_category())

        url = str(respx.calls[0].request.url)
        assert "f_SB2=4" in url
        assert "software+engineer" in url or "software%20engineer" in url
        assert "Singapore" in url or "singapore" in url.lower()

    @respx.mock
    def test_url_includes_experience_level(self):
        respx.get(url__startswith="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search").mock(
            return_value=httpx.Response(200, text="")
        )

        category = _make_category(experience_level="entry,mid-senior")
        with LinkedInScraper(_make_config()) as scraper:
            scraper.search(category)

        url = str(respx.calls[0].request.url)
        assert "f_E=2,4" in url

    @respx.mock
    def test_clean_url_removes_tracking(self):
        fixture = _load_fixture("search_response.html")
        respx.get(url__startswith="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search").mock(
            return_value=httpx.Response(200, text=fixture)
        )

        with LinkedInScraper(_make_config()) as scraper:
            jobs = scraper.search(_make_category())

        assert "?" not in jobs[0].url
        assert "trackingId" not in jobs[0].url

    @respx.mock
    def test_handles_404(self):
        respx.get(url__startswith="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search").mock(
            return_value=httpx.Response(404)
        )

        with LinkedInScraper(_make_config()) as scraper:
            jobs = scraper.search(_make_category())

        assert jobs == []

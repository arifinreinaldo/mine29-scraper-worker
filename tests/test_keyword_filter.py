import pytest

from src.keyword_filter import filter_visa_jobs, is_visa_excluded
from src.models import Job


def _make_job(title: str = "Software Engineer", company: str = "Tech Corp", **kwargs) -> Job:
    defaults = dict(
        uuid="test-uuid",
        category="IT",
        location="Singapore",
        posting_date="2026-03-15",
        url="https://www.linkedin.com/jobs/view/test-uuid",
    )
    defaults.update(kwargs)
    return Job(title=title, company=company, **defaults)


class TestIsVisaExcluded:
    @pytest.mark.parametrize(
        "title",
        [
            "Software Engineer (SC/PR only)",
            "Data Analyst - SC/PR Only",
            "Marketing Manager (Singaporeans Only)",
            "Developer - Singapore Citizens Only",
            "Engineer (PR Only)",
            "Analyst - No Visa Sponsorship",
            "PM - Visa Not Sponsored",
            "Dev - No Sponsorship",
            "Engineer - Singapore Citizenship Required",
            "Analyst (Permanent Residents Only)",
            "Developer - No Work Pass",
        ],
    )
    def test_excludes_no_visa_titles(self, title):
        job = _make_job(title=title)
        assert is_visa_excluded(job) is True

    @pytest.mark.parametrize(
        "title",
        [
            "Software Engineer",
            "Senior Data Analyst",
            "Marketing Graduate Program",
            "Junior Developer - Visa Sponsored",
            "Full Stack Engineer",
            "Project Manager",
            "PR Manager",  # PR = public relations, not permanent resident
        ],
    )
    def test_keeps_normal_titles(self, title):
        job = _make_job(title=title)
        assert is_visa_excluded(job) is False

    def test_case_insensitive(self):
        job = _make_job(title="Engineer - VISA NOT SPONSORED")
        assert is_visa_excluded(job) is True

    def test_checks_company_too(self):
        job = _make_job(title="Engineer", company="SC/PR only firm")
        assert is_visa_excluded(job) is True


class TestFilterVisaJobs:
    def test_filters_correctly(self):
        jobs = [
            _make_job(uuid="1", title="Software Engineer"),
            _make_job(uuid="2", title="Analyst (SC/PR only)"),
            _make_job(uuid="3", title="Developer - Visa Sponsored"),
            _make_job(uuid="4", title="PM - Singaporeans Only"),
        ]
        result = filter_visa_jobs(jobs)
        assert len(result) == 2
        assert result[0].uuid == "1"
        assert result[1].uuid == "3"

    def test_empty_list(self):
        assert filter_visa_jobs([]) == []

    def test_all_pass(self):
        jobs = [
            _make_job(uuid="1", title="Software Engineer"),
            _make_job(uuid="2", title="Data Analyst"),
        ]
        result = filter_visa_jobs(jobs)
        assert len(result) == 2

    def test_all_filtered(self):
        jobs = [
            _make_job(uuid="1", title="Engineer (SC/PR only)"),
            _make_job(uuid="2", title="Analyst - No Visa"),
        ]
        result = filter_visa_jobs(jobs)
        assert len(result) == 0

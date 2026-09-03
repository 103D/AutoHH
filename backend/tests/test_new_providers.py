"""Unit tests for the new job source providers."""

import json

import pytest

from app.core.exceptions import JobSourceError, NotFoundError
from app.providers.jobs.factory import create_job_provider
from app.providers.jobs.habr_career import HabrCareerProvider
from app.providers.jobs.hh_remote import HeadHunterRemoteProvider
from app.providers.jobs.jsonld import (
    extract_jobposting_blocks,
    jobposting_to_rawjob,
    stable_external_id,
    strip_html,
)
from app.providers.jobs.manual import ManualProvider
from app.providers.jobs.superjob import SuperJobProvider
from app.providers.jobs.zarplata import ZarplataProvider

SAMPLE_JOBPOSTING = {
    "@context": "https://schema.org/",
    "@type": "JobPosting",
    "title": "Data Analyst (BI)",
    "name": "Data Analyst (BI)",
    "description": "<p>We need a <b>strong</b> analyst with SQL &amp; Python.</p>",
    "hiringOrganization": {"@type": "Organization", "name": "Kaspi.kz"},
    "jobLocation": {
        "@type": "Place",
        "address": {"@type": "PostalAddress", "addressLocality": "Алматы"},
    },
    "datePosted": "2026-08-20T10:00:00+06:00",
    "employmentType": "FULL_TIME",
    "jobLocationType": "TELECOMMUTE",
    "experienceRequirements": "от 3 лет",
    "identifier": {"@type": "PropertyValue", "name": "habr", "value": "v-777"},
    "baseSalary": {
        "@type": "MonetaryAmount",
        "value": {
            "@type": "QuantitativeValue",
            "minValue": 500000,
            "maxValue": 800000,
            "unitText": "KZT",
        },
    },
    "@id": "/vacancies/v-777",
}

HTML_PAGE = f"""
<html><head>
<script type="application/ld+json">{json.dumps(SAMPLE_JOBPOSTING)}</script>
<script type="application/ld+json">not a json</script>
</head><body>jobs list</body></html>
"""


class TestJsonLdHelpers:
    """Tests for shared JSON-LD scraping helpers."""

    def test_strip_html(self):
        assert strip_html("<p>We need a <b>strong</b> analyst.</p>") == "We need a strong analyst."

    def test_extract_jobposting_blocks(self):
        postings = extract_jobposting_blocks(HTML_PAGE)

        assert len(postings) == 1
        assert postings[0]["identifier"]["value"] == "v-777"

    def test_extract_no_postings_returns_empty(self):
        assert extract_jobposting_blocks("<html><body>nothing here</body></html>") == []

    def test_jobposting_to_rawjob_full(self):
        kwargs = jobposting_to_rawjob(SAMPLE_JOBPOSTING, "https://career.habr.com")

        assert kwargs["external_id"] == "v-777"
        assert kwargs["title"] == "Data Analyst (BI)"
        assert kwargs["company"] == "Kaspi.kz"
        assert kwargs["location"] == "Алматы"
        assert kwargs["url"] == "https://career.habr.com/vacancies/v-777"
        assert kwargs["salary_min"] == 500000
        assert kwargs["salary_max"] == 800000
        assert kwargs["currency"] == "KZT"
        assert kwargs["employment_type"] == "full_time"
        assert kwargs["work_format"] == "remote"
        assert kwargs["experience_required"] == 3
        assert "strong" in kwargs["description"]
        assert "&" in kwargs["description"]  # &amp; decoded
        assert kwargs["published_at"] is not None

    def test_jobposting_relative_url_and_url_hash_id(self):
        posting = {
            "@type": "JobPosting",
            "title": "Analyst",
            "url": "/vacancies/abc-xyz",
        }
        kwargs = jobposting_to_rawjob(posting, "https://zarplata.ru")

        assert kwargs["url"] == "https://zarplata.ru/vacancies/abc-xyz"
        assert kwargs["external_id"] == stable_external_id("https://zarplata.ru/vacancies/abc-xyz")

    def test_stable_external_id_deterministic(self):
        assert stable_external_id("https://x/1") == stable_external_id("https://x/1")
        assert stable_external_id("https://x/1") != stable_external_id("https://x/2")

class TestSuperJobProvider:
    """Tests for the SuperJob API provider."""

    def test_headers_require_api_key(self):
        provider = SuperJobProvider(config={})

        with pytest.raises(JobSourceError, match="api_key"):
            provider._headers()

    def test_headers_with_api_key(self):
        provider = SuperJobProvider(config={"api_key": "abc123"})
        assert provider._headers() == {"X-api-app-id": "abc123"}

    def test_build_params_defaults(self):
        provider = SuperJobProvider(config={"remote": True})
        params = provider._build_params({"text": "analyst"}, 50)

        assert params["count"] == 50
        assert params["keywords[]"] == "analyst"
        assert SuperJobProvider.CATALOGUE_REMOTE in params["catalogues[]"]

    def test_build_params_no_remote_by_default(self):
        provider = SuperJobProvider(config={})
        params = provider._build_params({}, 10)

        assert "catalogues[]" not in params
        assert params["count"] == 10

    def test_parse_vacancy(self):
        provider = SuperJobProvider()
        data = {
            "id": 123456,
            "profession": "Аналитик данных",
            "firm_name": "Tech Company",
            "town": {"name": "Алматы"},
            "payment_from": 400000,
            "payment_to": 600000,
            "currency": "kzt",
            "link": "https://superjob.ru/vacancy/123456.html",
            "date_published": 1755500000,
            "type_of_work": {"id": 6, "title": "Полный рабочий день"},
            "place_of_work": {"id": 3, "title": "Удалённая работа"},
            "candidat": {
                "requirements": "Знание SQL и Python",
                "liability": "Анализ данных",
            },
        }

        raw_job = provider._parse_vacancy(data)

        assert raw_job.external_id == "123456"
        assert raw_job.title == "Аналитик данных"
        assert raw_job.company == "Tech Company"
        assert raw_job.location == "Алматы"
        assert raw_job.salary_min == 400000
        assert raw_job.salary_max == 600000
        assert raw_job.currency == "KZT"
        assert raw_job.employment_type == "full_time"
        assert raw_job.work_format == "remote"
        assert raw_job.url == "https://superjob.ru/vacancy/123456.html"
        assert raw_job.published_at is not None
        assert "SQL" in raw_job.description
        assert raw_job.raw_data == data

    def test_parse_vacancy_zero_salary_becomes_none(self):
        provider = SuperJobProvider()
        raw_job = provider._parse_vacancy(
            {"id": 1, "profession": "X", "payment_from": 0, "payment_to": 0, "currency": "rur"}
        )

        assert raw_job.salary_min is None
        assert raw_job.salary_max is None
        assert raw_job.currency == "RUB"


class TestHabrCareerProvider:
    """Tests for the Habr Career JSON-LD provider."""

    def test_build_params_defaults_remote(self):
        provider = HabrCareerProvider(config={"query": "BI analyst"})
        params = provider._build_params(None)

        assert params["q"] == "BI analyst"
        assert params["remote"] == "true"
        assert params["page"] == 1

    def test_build_params_filters_override(self):
        provider = HabrCareerProvider(config={"query": "BI analyst", "remote": True})
        params = provider._build_params({"text": "python", "remote": False, "page": 2})

        assert params["q"] == "python"
        assert "remote" not in params
        assert params["page"] == 2

    def test_parse_jobposting(self):
        provider = HabrCareerProvider()
        raw_job = provider._parse_jobposting(SAMPLE_JOBPOSTING)

        assert raw_job.title == "Data Analyst (BI)"
        assert raw_job.company == "Kaspi.kz"
        assert raw_job.url.startswith("https://career.habr.com/vacancies/")


class TestZarplataProvider:
    """Tests for the Zarplata.ru JSON-LD provider."""

    def test_build_params(self):
        provider = ZarplataProvider(config={"query": "аналитик"})
        params = provider._build_params({"text": "data analyst"})

        assert params["text"] == "data analyst"
        assert "remote" not in params

    def test_build_params_remote_enabled(self):
        provider = ZarplataProvider(config={"remote": True})
        assert provider._build_params(None)["remote"] == "true"

    def test_parse_jobposting(self):
        provider = ZarplataProvider()
        raw_job = provider._parse_jobposting(SAMPLE_JOBPOSTING)

        assert raw_job.title == "Data Analyst (BI)"
        assert raw_job.url.startswith("https://zarplata.ru/vacancies/")

class TestHeadHunterRemoteProvider:
    """Tests for the HH remote-vacancy provider."""

    def test_inherits_hh_kz_parsing(self):
        from app.providers.jobs.hh_kz import HeadHunterKZProvider

        provider = HeadHunterRemoteProvider()
        assert isinstance(provider, HeadHunterKZProvider)

    def test_default_filter_is_remote(self):
        provider = HeadHunterRemoteProvider(config={})
        filters = provider._build_filters(None)

        assert filters["schedule"] == "remote"  # area default ("40") is applied by the base provider

    def test_config_overrides_defaults(self):
        provider = HeadHunterRemoteProvider(config={"filters": {"area": "160", "text": "bi"}})
        filters = provider._build_filters(None)

        assert filters["schedule"] == "remote"  # default kept
        assert filters["area"] == "160"  # config override
        assert filters["text"] == "bi"

    def test_call_filters_override_config(self):
        provider = HeadHunterRemoteProvider(config={"filters": {"text": "bi"}})
        filters = provider._build_filters({"text": "analyst", "experience": "between1And3"})

        assert filters["text"] == "analyst"
        assert filters["experience"] == "between1And3"
        assert filters["schedule"] == "remote"


class TestManualProvider:
    """Tests for the manual job source provider."""

    def _provider(self) -> ManualProvider:
        return ManualProvider(
            config={
                "jobs": [
                    {
                        "external_id": "li-1",
                        "title": "Data Analyst",
                        "company": "Kaspi",
                        "description": "SQL, Python",
                        "url": "https://linkedin.com/jobs/1",
                        "location": "Almaty",
                        "salary_min": 500000,
                        "salary_max": 800000,
                        "currency": "KZT",
                        "work_format": "remote",
                    },
                    {
                        "title": "BI Analyst",
                        "company": "Halyk",
                        "description": "Power BI",
                        "url": "https://linkedin.com/jobs/2",
                    },
                    "not-a-dict",
                ]
            }
        )

    async def test_fetch_jobs_returns_raw_jobs(self):
        provider = self._provider()
        jobs = await provider.fetch_jobs()

        assert len(jobs) == 2
        first = jobs[0]
        assert first.external_id == "li-1"
        assert first.title == "Data Analyst"
        assert first.salary_max == 800000

        # Missing external_id is generated
        assert jobs[1].external_id.startswith("manual-")

    async def test_fetch_jobs_text_filter(self):
        provider = self._provider()
        jobs = await provider.fetch_jobs(filters={"text": "power bi"})

        assert len(jobs) == 1
        assert jobs[0].title == "BI Analyst"

    async def test_fetch_jobs_limit(self):
        provider = self._provider()
        jobs = await provider.fetch_jobs(limit=1)

        assert len(jobs) == 1

    async def test_fetch_jobs_invalid_config(self):
        provider = ManualProvider(config={"jobs": "not-a-list"})
        assert await provider.fetch_jobs() == []

    async def test_get_job_details_found(self):
        provider = self._provider()
        job = await provider.get_job_details("li-1")

        assert job.title == "Data Analyst"

    async def test_get_job_details_not_found(self):
        provider = self._provider()

        with pytest.raises(NotFoundError):
            await provider.get_job_details("missing")


class TestRemoteOkProvider:
    """Tests for the RemoteOK public API provider."""

    def test_parse_vacancy_full(self):
        from app.providers.jobs.remote_ok import RemoteOkProvider

        provider = RemoteOkProvider()

        data = {
            "id": "1137268",
            "position": "Amazon Specialist",
            "company": "Volar Fashion",
            "description": "<p>We need a <b>strong</b> analyst.</p>",
            "location": "Agra, ",
            "url": "https://remoteok.com/remote-jobs/remote-amazon-specialist-1137268",
            "apply_url": "https://remoteok.com/remote-jobs/apply",
            "salary_min": 40000,
            "salary_max": 60000,
            "date": "2026-09-02T05:59:36+00:00",
        }

        job = provider._parse_vacancy(data)



        assert job.external_id == "1137268"
        assert job.title == "Amazon Specialist"
        assert job.company == "Volar Fashion"
        assert job.work_format == "remote"
        assert job.salary_min == 40000
        assert job.salary_max == 60000
        assert "strong" in job.description
        assert "<" not in job.description
        assert job.url == "https://remoteok.com/remote-jobs/remote-amazon-specialist-1137268"
        assert job.published_at is not None

    def test_parse_vacancy_minimal(self):
        from app.providers.jobs.remote_ok import RemoteOkProvider

        provider = RemoteOkProvider()
        data = {"id": "1", "position": "Data Analyst", "salary_min": 0, "salary_max": 0}

        job = provider._parse_vacancy(data)



        assert job.title == "Data Analyst"
        assert job.salary_min is None
        assert job.salary_max is None
        assert job.location is None
        assert job.work_format == "remote"
        assert job.currency is None
        assert job.description == ""


class TestFactoryRegistration:
    """Tests that all new providers are registered in the factory."""

    @pytest.mark.parametrize(
        "source_type,expected_class",
        [
            ("hh_kz", "HeadHunterKZProvider"),
            ("hh_remote", "HeadHunterRemoteProvider"),
            ("habr_career", "HabrCareerProvider"),
            ("zarplata", "ZarplataProvider"),
            ("superjob", "SuperJobProvider"),
            ("manual", "ManualProvider"),
            ("remote_ok", "RemoteOkProvider"),
        ],
    )
    def test_factory_creates_providers(self, source_type, expected_class):
        provider = create_job_provider(source_type, {})
        assert type(provider).__name__ == expected_class

    def test_factory_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown job source type"):
            create_job_provider("nonexistent", {})

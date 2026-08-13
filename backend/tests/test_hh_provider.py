import pytest

from datetime import datetime

from app.providers.jobs.hh_kz import HeadHunterKZProvider

def test_parse_vacancy():
    """Test parsing HH API vacancy data."""
    
    provider = HeadHunterKZProvider()
    
    # Sample HH API response
    hh_data = {
        "id": "123456",
        "name": "Senior Python Developer",
        "employer": {
            "name": "Tech Company"
        },
        "area": {
            "name": "Almaty"
        },
        "salary": {
            "from": 400000,
            "to": 600000,
            "currency": "KZT"
        },
        "employment": {
            "id": "full"
        },
        "schedule": {
            "id": "remote"
        },
        "description": "We are looking for a senior Python developer...",
        "alternate_url": "https://hh.kz/vacancy/123456",
        "published_at": "2026-08-12T10:00:00+06:00"
    }
    
    raw_job = provider._parse_vacancy(hh_data)
    
    assert raw_job.external_id == "123456"
    assert raw_job.title == "Senior Python Developer"
    assert raw_job.company == "Tech Company"
    assert raw_job.location == "Almaty"
    assert raw_job.salary_min == 400000
    assert raw_job.salary_max == 600000
    assert raw_job.currency == "KZT"
    assert raw_job.employment_type == "full"
    assert raw_job.work_format == "remote"
    assert raw_job.url == "https://hh.kz/vacancy/123456"
    assert raw_job.description == "We are looking for a senior Python developer..."
    assert isinstance(raw_job.published_at, datetime)
    assert raw_job.raw_data == hh_data

def test_parse_vacancy_minimal():
    """Test parsing vacancy with minimal data."""
    
    provider = HeadHunterKZProvider()
    
    hh_data = {
        "id": "789",
        "name": "Junior Developer",
        "employer": {
            "name": "StartUp"
        },
        "snippet": {
            "requirement": "Basic programming skills.",
            "responsibility": "Write code."
        },
        "alternate_url": "https://hh.kz/vacancy/789"
    }
    
    raw_job = provider._parse_vacancy(hh_data)
    
    assert raw_job.external_id == "789"
    assert raw_job.title == "Junior Developer"
    assert raw_job.company == "StartUp"
    assert raw_job.salary_min is None
    assert raw_job.salary_max is None
    assert raw_job.location is None
    assert "Basic programming skills" in raw_job.description
    assert "Write code" in raw_job.description
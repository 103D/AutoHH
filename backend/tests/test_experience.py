"""Tests for deterministic experience extraction utilities."""

from app.utils.experience import (
    experience_years_from_hh_id,
    extract_required_experience_years,
)


def test_russian_patterns():
    assert extract_required_experience_years("Требуется 3+ года опыта") == 3
    assert extract_required_experience_years("опыт работы от 5 лет") == 5
    assert extract_required_experience_years("Опыт: 2 года в аналитике") == 2
    assert extract_required_experience_years("от 7 лет в data science") == 7


def test_english_patterns():
    assert extract_required_experience_years("We require 3+ years of experience") == 3
    assert extract_required_experience_years("5+ years experience with SQL") == 5
    assert extract_required_experience_years("7+ yrs in analytics") == 7


def test_no_experience_requirement():
    assert extract_required_experience_years("No degree required") is None
    assert extract_required_experience_years(None) is None
    assert extract_required_experience_years("") is None
    assert extract_required_experience_years("0") is None


def test_hh_experience_ids():
    assert experience_years_from_hh_id("noExperience") == 0
    assert experience_years_from_hh_id("between1And3") == 1
    assert experience_years_from_hh_id("between3And6") == 3
    assert experience_years_from_hh_id("moreThan6") == 6
    assert experience_years_from_hh_id(None) is None
    assert experience_years_from_hh_id("unknown") is None

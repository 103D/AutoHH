"""Tests for UserPolicy evaluation."""

import pytest

from app.hermes.policy import UserPolicy


class _FakeJob:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "fake-job-id")
        self.title = kwargs.get("title", "Data Analyst")
        self.company = kwargs.get("company", "TestCo")
        self.location = kwargs.get("location", "Москва")
        self.salary_min = kwargs.get("salary_min", 100000)
        self.salary_max = kwargs.get("salary_max", 200000)
        self.currency = kwargs.get("currency", "RUB")
        self.employment_type = kwargs.get("employment_type", "full_time")
        self.work_format = kwargs.get("work_format", "remote")
        self.experience_required = kwargs.get("experience_required", 3)
        self.specializations = kwargs.get("specializations", ["DATA_ANALYST"])
        self.description = kwargs.get("description", "")


class _FakeMatch:
    def __init__(self, score=80):
        self.score = score


class _FakeProfile:
    def __init__(self, **kwargs):
        self.experience_years = kwargs.get("experience_years", 3)
        self.experience_level = kwargs.get("experience_level", "middle")
        self.desired_salary_min = kwargs.get("desired_salary_min", 100000)
        self.desired_salary_max = kwargs.get("desired_salary_max", 200000)
        self.location = kwargs.get("location", "Москва")
        self.employment_types = kwargs.get("employment_types", ["full_time"])
        self.work_formats = kwargs.get("work_formats", ["remote"])
        self.skills = kwargs.get("skills", ["sql", "python"])


class TestUserPolicyNoConstraints:
    def test_empty_policy_permits_everything(self):
        policy = UserPolicy()
        permitted, reasons = policy.evaluate(_FakeJob(), _FakeMatch(), _FakeProfile())
        assert permitted is True
        assert reasons == []

    def test_empty_policy_with_none_fields(self):
        policy = UserPolicy()
        job = _FakeJob(
            location=None, salary_max=None, experience_required=None,
            specializations=None, employment_type=None, work_format=None,
        )
        permitted, reasons = policy.evaluate(job, _FakeMatch(), _FakeProfile())
        assert permitted is True
        assert reasons == []


class TestUserPolicyMinScore:
    def test_score_above_min_permits(self):
        policy = UserPolicy(min_score=70)
        permitted, reasons = policy.evaluate(_FakeJob(), _FakeMatch(score=80), _FakeProfile())
        assert permitted is True
        assert reasons == []

    def test_score_at_min_permits(self):
        policy = UserPolicy(min_score=70)
        permitted, reasons = policy.evaluate(_FakeJob(), _FakeMatch(score=70), _FakeProfile())
        assert permitted is True
        assert reasons == []

    def test_score_below_min_denies(self):
        policy = UserPolicy(min_score=70)
        permitted, reasons = policy.evaluate(_FakeJob(), _FakeMatch(score=65), _FakeProfile())
        assert permitted is False
        assert any("score 65" in r for r in reasons)


class TestUserPolicySalary:
    def test_salary_within_range_permits(self):
        policy = UserPolicy(min_salary_max=100000, max_salary_max=250000)
        permitted, reasons = policy.evaluate(_FakeJob(salary_max=200000), _FakeMatch(), _FakeProfile())
        assert permitted is True

    def test_salary_below_min_denies(self):
        policy = UserPolicy(min_salary_max=150000)
        permitted, reasons = policy.evaluate(_FakeJob(salary_max=120000), _FakeMatch(), _FakeProfile())
        assert permitted is False
        assert any("salary_max" in r and "min_salary_max" in r for r in reasons)

    def test_salary_above_max_denies(self):
        policy = UserPolicy(max_salary_max=200000)
        permitted, reasons = policy.evaluate(_FakeJob(salary_max=250000), _FakeMatch(), _FakeProfile())
        assert permitted is False
        assert any("salary_max" in r and "max_salary_max" in r for r in reasons)


class TestUserPolicyLocation:
    def test_matching_location_permits(self):
        policy = UserPolicy(locations=["Москва", "СПб"])
        permitted, reasons = policy.evaluate(_FakeJob(location="Москва"), _FakeMatch(), _FakeProfile())
        assert permitted is True

    def test_non_matching_location_denies(self):
        policy = UserPolicy(locations=["Москва"])
        permitted, reasons = policy.evaluate(_FakeJob(location="Казань"), _FakeMatch(), _FakeProfile())
        assert permitted is False
        assert any("Казань" in r for r in reasons)

    def test_location_case_insensitive(self):
        policy = UserPolicy(locations=["москва"])
        permitted, reasons = policy.evaluate(_FakeJob(location="Москва"), _FakeMatch(), _FakeProfile())
        assert permitted is True


class TestUserPolicySpecialization:
    def test_matching_specialization_permits(self):
        policy = UserPolicy(specializations=["DATA_ANALYST"])
        permitted, reasons = policy.evaluate(_FakeJob(specializations=["DATA_ANALYST"]), _FakeMatch(), _FakeProfile())
        assert permitted is True

    def test_no_matching_specialization_denies(self):
        policy = UserPolicy(specializations=["BI_ANALYST"])
        permitted, reasons = policy.evaluate(_FakeJob(specializations=["DATA_ANALYST"]), _FakeMatch(), _FakeProfile())
        assert permitted is False
        assert any("specializations" in r for r in reasons)

    def test_specialization_case_insensitive(self):
        policy = UserPolicy(specializations=["data_analyst"])
        permitted, reasons = policy.evaluate(_FakeJob(specializations=["DATA_ANALYST"]), _FakeMatch(), _FakeProfile())
        assert permitted is True


class TestUserPolicyEmploymentType:
    def test_matching_employment_type_permits(self):
        policy = UserPolicy(employment_types=["full_time"])
        permitted, reasons = policy.evaluate(_FakeJob(employment_type="full_time"), _FakeMatch(), _FakeProfile())
        assert permitted is True

    def test_non_matching_employment_type_denies(self):
        policy = UserPolicy(employment_types=["full_time"])
        permitted, reasons = policy.evaluate(_FakeJob(employment_type="part_time"), _FakeMatch(), _FakeProfile())
        assert permitted is False
        assert any("employment_type" in r for r in reasons)


class TestUserPolicyWorkFormat:
    def test_matching_work_format_permits(self):
        policy = UserPolicy(work_formats=["remote"])
        permitted, reasons = policy.evaluate(_FakeJob(work_format="remote"), _FakeMatch(), _FakeProfile())
        assert permitted is True

    def test_non_matching_work_format_denies(self):
        policy = UserPolicy(work_formats=["remote"])
        permitted, reasons = policy.evaluate(_FakeJob(work_format="office"), _FakeMatch(), _FakeProfile())
        assert permitted is False
        assert any("work_format" in r for r in reasons)


class TestUserPolicyExcludedCompanies:
    def test_non_excluded_company_permits(self):
        policy = UserPolicy(excluded_companies=["bad_corp"])
        permitted, reasons = policy.evaluate(_FakeJob(company="GoodCorp"), _FakeMatch(), _FakeProfile())
        assert permitted is True

    def test_excluded_company_denies(self):
        policy = UserPolicy(excluded_companies=["evil_corp"])
        permitted, reasons = policy.evaluate(_FakeJob(company="Evil_Corp"), _FakeMatch(), _FakeProfile())
        assert permitted is False
        assert any("excluded" in r for r in reasons)


class TestUserPolicyExperienceGap:
    def test_within_gap_permits(self):
        policy = UserPolicy(max_experience_gap_years=2.0)
        permitted, reasons = policy.evaluate(
            _FakeJob(experience_required=4), _FakeMatch(), _FakeProfile(experience_years=3)
        )
        assert permitted is True

    def test_exceeding_gap_denies(self):
        policy = UserPolicy(max_experience_gap_years=1.0)
        permitted, reasons = policy.evaluate(
            _FakeJob(experience_required=5), _FakeMatch(), _FakeProfile(experience_years=3)
        )
        assert permitted is False
        assert any("gap" in r for r in reasons)

    def test_no_experience_required_no_gap(self):
        policy = UserPolicy(max_experience_gap_years=1.0)
        permitted, reasons = policy.evaluate(
            _FakeJob(experience_required=None), _FakeMatch(), _FakeProfile(experience_years=3)
        )
        assert permitted is True


class TestUserPolicyCompound:
    def test_multiple_violations_collected(self):
        policy = UserPolicy(min_score=80, locations=["Москва"])
        permitted, reasons = policy.evaluate(
            _FakeJob(location="Казань"), _FakeMatch(score=60), _FakeProfile()
        )
        assert permitted is False
        assert len(reasons) == 2

    def test_all_constraints_satisfied(self):
        policy = UserPolicy(
            min_score=70,
            min_salary_max=100000,
            max_salary_max=250000,
            locations=["Москва"],
            specializations=["DATA_ANALYST"],
            employment_types=["full_time"],
            work_formats=["remote"],
            max_experience_gap_years=3.0,
        )
        permitted, reasons = policy.evaluate(
            _FakeJob(
                salary_max=200000,
                location="Москва",
                specializations=["DATA_ANALYST"],
                employment_type="full_time",
                work_format="remote",
                experience_required=4,
            ),
            _FakeMatch(score=85),
            _FakeProfile(experience_years=3),
        )
        assert permitted is True
        assert reasons == []

"""Tests for anti-hallucination validation."""

from app.services.validation import AntiHallucinationValidator, ValidationResult


def test_validate_resume_no_hallucinations():
    """Test that valid resume adaptation passes."""
    validator = AntiHallucinationValidator()

    original = (
        "Data Analyst with 4 years of experience. "
        "Skills: Python, SQL, PostgreSQL, Tableau."
    )
    adapted = (
        "Data Analyst with 4 years of experience. "
        "Proficient in Python, SQL, PostgreSQL, and Tableau."
    )

    result = validator.validate_resume(original, adapted)
    assert result.is_valid is True
    assert result.issues == []


def test_validate_resume_detects_hallucinated_skill():
    """Test that hallucinated skill is detected."""
    validator = AntiHallucinationValidator()

    original = "Data Analyst with Python and SQL skills."
    adapted = "Data Analyst with Python, SQL, and Kubernetes skills."

    result = validator.validate_resume(original, adapted)
    assert result.is_valid is False
    assert any("kubernetes" in issue for issue in result.issues)


def test_validate_resume_detects_hallucinated_number():
    """Test that hallucinated number is detected."""
    validator = AntiHallucinationValidator()

    original = "Data Analyst with 3 years of experience."
    adapted = "Data Analyst with 10 years of experience."

    result = validator.validate_resume(original, adapted)
    assert result.is_valid is False
    assert any("10" in issue for issue in result.issues)


def test_validate_resume_allows_extra_skills():
    """Test that allowed_skills parameter permits additional skills."""
    validator = AntiHallucinationValidator()

    original = "Data Analyst with Python skills."
    adapted = "Data Analyst with Python and dbt skills."

    result = validator.validate_resume(original, adapted, allowed_skills=["dbt"])
    assert result.is_valid is True


def test_validate_resume_allows_skill_confirmed_by_candidate_profile():
    """Structured candidate facts may authorize an omitted source-resume skill."""
    validator = AntiHallucinationValidator()

    original = "Data Analyst with Python skills."
    adapted = "Data Analyst with Python and PostgreSQL skills."
    profile = {
        "skills": ["Python"],
        "technologies": {"databases": ["PostgreSQL"]},
        "experience_years": 2,
        "desired_positions": ["Data Analyst"],
    }

    result = validator.validate_resume(original, adapted, candidate_profile=profile)

    assert result.is_valid is True
    assert result.issues == []


def test_validate_resume_rejects_fact_absent_from_source_and_profile():
    """Profile-aware validation must still reject unsupported generated claims."""
    validator = AntiHallucinationValidator()

    original = "Data Analyst with Python skills."
    adapted = "Data Analyst with Python, PostgreSQL, and 10 years of experience."
    profile = {
        "skills": ["Python"],
        "technologies": {"databases": ["PostgreSQL"]},
        "experience_years": 2,
        "desired_positions": ["Data Analyst"],
    }

    result = validator.validate_resume(original, adapted, candidate_profile=profile)

    assert result.is_valid is False
    assert any("10" in issue for issue in result.issues)


def test_validate_resume_does_not_extract_sql_from_postgresql():
    """Technology extraction must respect token boundaries."""
    validator = AntiHallucinationValidator()

    result = validator.validate_resume(
        "Data Analyst with PostgreSQL.",
        "Data Analyst with PostgreSQL.",
    )

    assert result.is_valid is True
    assert result.issues == []


def test_validate_resume_allows_structured_experience_project_and_certificate():
    validator = AntiHallucinationValidator()
    profile = {
        "skills": ["Python", "SQL"],
        "technologies": {},
        "desired_positions": ["Data Analyst"],
        "experience": [
            {
                "company": "Safia",
                "title": "Аналитик данных",
                "achievements": ["Автоматизировал отчётность"],
            }
        ],
        "projects": [{"name": "Retail Dashboard", "role": "Data Analyst"}],
        "certifications": [{"name": "Google Data Analytics", "issuer": "Google"}],
    }
    adapted = (
        "Работал в Safia как аналитик данных. "
        "Проект Retail Dashboard. "
        "Сертификат Google Data Analytics."
    )

    result = validator.validate_resume(
        "Python and SQL analyst.",
        adapted,
        candidate_profile=profile,
    )

    assert result.is_valid is True
    assert result.issues == []


def test_validate_resume_rejects_unsupported_company_project_and_certificate():
    validator = AntiHallucinationValidator()
    profile = {
        "skills": ["Python"],
        "technologies": {},
        "desired_positions": ["Data Analyst"],
        "experience": [{"company": "Safia", "title": "Аналитик данных"}],
        "projects": [{"name": "Retail Dashboard"}],
        "certifications": [{"name": "Google Data Analytics"}],
    }
    adapted = (
        "Worked at Amazon. "
        "Project Fraud Detection Platform. "
        "Certification AWS Solutions Architect."
    )

    result = validator.validate_resume(
        "Data Analyst with Python.",
        adapted,
        candidate_profile=profile,
    )

    assert result.is_valid is False
    assert any("amazon" in issue.lower() for issue in result.issues)
    assert any("fraud detection platform" in issue.lower() for issue in result.issues)
    assert any("aws solutions architect" in issue.lower() for issue in result.issues)


def test_validate_resume_does_not_extract_product_from_production():
    validator = AntiHallucinationValidator()

    result = validator.validate_resume(
        "Data Analyst with Python.",
        "Data Analyst who built production systems with Python.",
    )

    assert result.is_valid is True
    assert not any("product" in issue.lower() for issue in result.issues)


def test_validate_cover_letter_valid():
    """Test that valid cover letter passes."""
    validator = AntiHallucinationValidator()

    profile = {
        "skills": ["Python", "SQL", "Tableau"],
        "technologies": {"databases": ["PostgreSQL"]},
        "experience_years": 4,
        "desired_positions": ["Data Analyst"],
    }
    cover_letter = (
        "I am a Data Analyst with 4 years of experience. "
        "I have strong skills in Python, SQL, PostgreSQL, and Tableau."
    )

    result = validator.validate_cover_letter(profile, cover_letter)
    assert result.is_valid is True


def test_validate_cover_letter_detects_hallucination():
    """Test that hallucinated fact in cover letter is detected."""
    validator = AntiHallucinationValidator()

    profile = {
        "skills": ["Python"],
        "technologies": {},
        "experience_years": 2,
        "desired_positions": ["Data Analyst"],
    }
    cover_letter = (
        "I am a Data Analyst with 10 years of experience. "
        "I have strong skills in Python and Kubernetes."
    )

    result = validator.validate_cover_letter(profile, cover_letter)
    assert result.is_valid is False
    assert any("10" in issue for issue in result.issues)
    assert any("kubernetes" in issue for issue in result.issues)


def test_validation_result_defaults():
    """Test ValidationResult defaults."""
    result = ValidationResult(is_valid=True)
    assert result.issues == []
    assert result.warnings == []

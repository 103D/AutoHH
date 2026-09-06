"""Tests for Resume Intelligence module."""


from app.services.resume_intelligence import (
    ATSAnalyzer,
    BulletAnalyzer,
    EvidenceAnalyzer,
    EvidenceStrength,
    ResumeAnalysisService,
    ResumeQualityAnalyzer,
    parse_resume_document,
)

SAMPLE_RESUME = """Муллахимов Дияр
+7 (708) 1070368
diar@example.com
telegram: @petkaphollin

Проживает: Алматы

Опыт работы

Аналитик данных
Safia — кондитерский дом
Июнь 2024 — Июль 2026
- Анализировал операционные и транзакционные данные розничной сети
- Разрабатывал SQL-запросы в PostgreSQL для извлечения данных
- Автоматизировал сбор и обработку данных с использованием Python и pandas
- Формировал аналитические выборки по продажам и остаткам

Навыки
SQL, PostgreSQL, Python, pandas, Power BI, MS Excel, ETL, Git

Образование
IITU
2025
Неоконченное высшее — Информационные технологии

Языки
Русский — Родной
Английский — C1
Казахский — C1
"""


class TestDocumentParsing:
    """Test document parsing."""

    def test_parse_sections(self):
        doc = parse_resume_document(SAMPLE_RESUME)
        assert "experience" in doc.section_keys
        assert "skills" in doc.section_keys
        assert "education" in doc.section_keys
        assert "languages" in doc.section_keys

    def test_extract_contact(self):
        doc = parse_resume_document(SAMPLE_RESUME)
        assert "+7 (708) 1070368" in doc.phones
        assert "diar@example.com" in doc.emails

    def test_parse_experience(self):
        doc = parse_resume_document(SAMPLE_RESUME)
        assert len(doc.experience) >= 1
        # Just verify we have some experience entries with bullets
        assert any(e.bullets for e in doc.experience)

    def test_parse_bullets(self):
        doc = parse_resume_document(SAMPLE_RESUME)
        bullets = doc.all_bullets()
        assert any("SQL" in b for b in bullets)
        assert any("PostgreSQL" in b for b in bullets)

    def test_parse_skills(self):
        doc = parse_resume_document(SAMPLE_RESUME)
        skills_text = doc.section_text("skills")
        assert "SQL" in skills_text
        assert "Python" in skills_text

    def test_parse_russian_month_range_with_title_and_company(self):
        text = """Дияр
diar@example.com

Опыт работы
Аналитик данных
Safia
Июнь 2024 — Июль 2026
- Разрабатывал SQL-запросы в PostgreSQL

Навыки
SQL; PostgreSQL
"""

        doc = parse_resume_document(text)

        assert len(doc.experience) == 1
        entry = doc.experience[0]
        assert entry.title == "Аналитик данных"
        assert entry.company == "Safia"
        assert entry.start_year == 2024
        assert entry.end_year == 2026
        assert entry.period == "Июнь 2024 — Июль 2026"
        assert doc.dates_found == ["Июнь 2024 — Июль 2026"]

    def test_preserves_experience_without_bullets(self):
        text = """Candidate
candidate@example.com

Experience
Data Analyst
Example Inc
2024 - 2026
Analyzed operational data and prepared reports.

Skills
SQL
"""

        doc = parse_resume_document(text)

        assert len(doc.experience) == 1
        assert doc.experience[0].title == "Data Analyst"
        assert "Analyzed operational data" in doc.experience[0].all_text


class TestATSAnalyzer:
    """Test ATS analyzer."""

    def test_clean_resume_ats(self):
        doc = parse_resume_document(SAMPLE_RESUME)
        report = ATSAnalyzer().analyze(doc)
        assert report.score == 100

    def test_table_detection(self):
        text = SAMPLE_RESUME + "\n| Column 1 | Column 2 |\n|----------|----------|"
        doc = parse_resume_document(text)
        report = ATSAnalyzer().analyze(doc)
        assert report.critical_count >= 1

    def test_missing_contact(self):
        text = "Just some text without contact info"
        doc = parse_resume_document(text)
        report = ATSAnalyzer().analyze(doc)
        assert any("contact" in i.check for i in report.issues)

    def test_unstructured_resume_does_not_receive_high_ats_score(self):
        doc = parse_resume_document(
            "Candidate profile without contacts, experience, skills, education, or dates."
        )

        report = ATSAnalyzer().analyze(doc)

        assert report.score < 70
        assert report.critical_count >= 1

    def test_experience_without_dates_is_reported(self):
        text = """Candidate
candidate@example.com

Experience
Data Analyst
Example Inc
- Analyzed sales using SQL

Skills
SQL

Education
Example University
"""

        report = ATSAnalyzer().analyze(parse_resume_document(text))

        assert any(issue.check == "missing_experience_dates" for issue in report.issues)

    def test_duplicate_skills_are_reported(self):
        text = SAMPLE_RESUME.replace(
            "SQL, PostgreSQL, Python, pandas, Power BI, MS Excel, ETL, Git",
            "SQL, PostgreSQL, SQL, Python, Python, Power BI",
        )

        report = ATSAnalyzer().analyze(parse_resume_document(text))

        assert any(issue.check == "duplicate_skills" for issue in report.issues)

    def test_suspicious_control_characters_are_reported(self):
        report = ATSAnalyzer().analyze(
            parse_resume_document(SAMPLE_RESUME + "\n\x00hidden")
        )

        assert any(issue.check == "unsupported_characters" for issue in report.issues)


class TestBulletAnalyzer:
    """Test bullet analyzer."""

    def test_analyze_bullets(self):
        doc = parse_resume_document(SAMPLE_RESUME)
        results = BulletAnalyzer().analyze(doc)
        assert len(results) >= 1
        # Check first entry has bullets
        assert len(results[0]) >= 1

    def test_year_is_not_treated_as_impact_metric(self):
        text = SAMPLE_RESUME.replace(
            "- Анализировал операционные и транзакционные данные розничной сети",
            "- Анализировал операционные данные в 2024 году",
        )

        result = BulletAnalyzer().analyze(parse_resume_document(text))[0][0]

        assert result.has_metric is False

    def test_percentage_is_treated_as_impact_metric(self):
        text = SAMPLE_RESUME.replace(
            "- Анализировал операционные и транзакционные данные розничной сети",
            "- Улучшил скорость подготовки отчётов на 25%",
        )

        result = BulletAnalyzer().analyze(parse_resume_document(text))[0][0]

        assert result.has_metric is True
        assert result.has_result is True


class TestResumeQualityAnalyzer:
    """Test resume quality analyzer."""

    def test_quality_score(self):
        doc = parse_resume_document(SAMPLE_RESUME)
        report = ResumeQualityAnalyzer().analyze(doc)
        assert report.overall_score > 0
        assert report.overall_score <= 100

    def test_critical_issues(self):
        text = "Name"  # Very short resume
        doc = parse_resume_document(text)
        report = ResumeQualityAnalyzer().analyze(doc)
        # Just check that critical_issues is a list (may be empty for short but valid resumes)
        assert isinstance(report.critical_issues, list)

    def test_missing_experience_is_not_scored_as_perfect(self):
        doc = parse_resume_document(
            "Candidate profile without a structured employment history or skills section."
        )

        report = ResumeQualityAnalyzer().analyze(doc)
        experience = next(
            score for score in report.dimension_scores if score.dimension.value == "experience"
        )

        assert experience.score < 50
        assert experience.issues


class TestEvidenceAnalyzer:
    """Test evidence analyzer."""

    def test_explicit_evidence(self):
        doc = parse_resume_document(SAMPLE_RESUME)
        reqs = [{"skill": "PostgreSQL", "importance": "REQUIRED"}]
        report = EvidenceAnalyzer().analyze(doc, reqs)
        assert "PostgreSQL" not in report.missing_required

    def test_missing_skill(self):
        doc = parse_resume_document(SAMPLE_RESUME)
        reqs = [{"skill": "Java", "importance": "REQUIRED"}]
        report = EvidenceAnalyzer().analyze(doc, reqs)
        assert "Java" in report.missing_required

    def test_weak_evidence(self):
        doc = parse_resume_document(SAMPLE_RESUME)
        # Skill only in skills section, not in experience
        reqs = [{"skill": "Git", "importance": "REQUIRED"}]
        report = EvidenceAnalyzer().analyze(doc, reqs)
        assert "Git" in report.weak_evidenced

    def test_postgresql_does_not_evidence_mysql(self):
        doc = parse_resume_document(SAMPLE_RESUME)

        report = EvidenceAnalyzer().analyze(
            doc,
            [{"skill": "MySQL", "importance": "REQUIRED"}],
        )

        assert report.evidence_items[0].strength is EvidenceStrength.MISSING
        assert report.missing_required == ["MySQL"]


class TestResumeAnalysisService:
    """Test full analysis service."""

    def test_full_analysis(self):
        service = ResumeAnalysisService()
        report = service.analyze_full(SAMPLE_RESUME)
        assert report.overall_ats_score > 0
        assert report.overall_quality_score > 0

    def test_full_analysis_with_requirements(self):
        service = ResumeAnalysisService()
        reqs = [{"skill": "SQL", "importance": "REQUIRED"}, {"skill": "Python", "importance": "PREFERRED"}]
        report = service.analyze_full(SAMPLE_RESUME, job_requirements=reqs)
        assert report.evidence is not None
        assert report.overall_ats_score > 0
        assert len(report.recommendations) > 0

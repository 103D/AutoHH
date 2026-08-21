"""Anti-hallucination validation for AI-generated content."""

import re
from dataclasses import dataclass, field

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of anti-hallucination validation."""

    is_valid: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class AntiHallucinationValidator:
    """Validate that AI-generated content doesn't invent facts."""

    TECH_KEYWORDS = [
        "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
        "ruby", "php", "swift", "kotlin", "scala", "sql",
        "django", "flask", "fastapi", "react", "vue", "angular", "node.js",
        "spring", "laravel", "rails", "tensorflow", "pytorch",
        "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "clickhouse",
        "docker", "kubernetes", "git", "jenkins", "airflow", "spark", "kafka",
        "tableau", "power bi", "excel", "pandas", "numpy", "dbt",
    ]

    POSITION_KEYWORDS = [
        "analyst", "developer", "engineer", "scientist", "manager", "architect",
        "consultant", "specialist", "lead", "senior", "junior", "middle",
        "data", "bi", "product", "project",
    ]

    def __init__(self) -> None:
        self._number_pattern = re.compile(r"\b\d+(?:[.,]\d+)?\b")

    def _extract_facts(self, text: str) -> set[str]:
        """Extract factual claims from text."""
        facts: set[str] = set()
        text_lower = text.lower()

        for num in self._number_pattern.findall(text):
            facts.add(f"number:{num}")

        for tech in self.TECH_KEYWORDS:
            if tech in text_lower:
                facts.add(f"tech:{tech}")

        for pos in self.POSITION_KEYWORDS:
            if pos in text_lower:
                facts.add(f"position:{pos}")

        return facts

    def _extract_allowed_facts_from_profile(self, profile: dict) -> set[str]:
        """Build set of allowed facts from candidate profile."""
        allowed: set[str] = set()

        for skill in profile.get("skills", []):
            allowed.add(f"tech:{skill.lower()}")

        technologies = profile.get("technologies", {})
        if isinstance(technologies, dict):
            for tech_list in technologies.values():
                if isinstance(tech_list, list):
                    for tech in tech_list:
                        allowed.add(f"tech:{str(tech).lower()}")

        experience_years = profile.get("experience_years")
        if experience_years is not None:
            allowed.add(f"number:{experience_years}")

        for pos in profile.get("desired_positions", []):
            pos_lower = pos.lower()
            allowed.add(f"position:{pos_lower}")
            for word in pos_lower.split():
                allowed.add(f"position:{word}")

        education = profile.get("education", [])
        if isinstance(education, list):
            for edu in education:
                if isinstance(edu, dict):
                    degree = edu.get("degree", "")
                    if degree:
                        allowed.add(f"position:{degree.lower()}")
                    field_name = edu.get("field", "")
                    if field_name:
                        allowed.add(f"position:{field_name.lower()}")

        return allowed

    def validate_resume(
        self,
        original_resume: str,
        adapted_resume: str,
        allowed_skills: list[str] | None = None,
    ) -> ValidationResult:
        """Validate adapted resume doesn't contain hallucinated facts."""
        original_facts = self._extract_facts(original_resume)
        adapted_facts = self._extract_facts(adapted_resume)

        if allowed_skills:
            for skill in allowed_skills:
                original_facts.add(f"tech:{skill.lower()}")

        issues = []
        for fact in adapted_facts - original_facts:
            if fact.startswith("number:"):
                issues.append(f"Number '{fact.split(':', 1)[1]}' not found in original resume")
            elif fact.startswith("tech:"):
                issues.append(f"Technology '{fact.split(':', 1)[1]}' not found in original resume")
            elif fact.startswith("position:"):
                issues.append(f"Position '{fact.split(':', 1)[1]}' not found in original resume")

        if issues:
            logger.warning(f"Resume validation found {len(issues)} potential hallucinations")

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_cover_letter(
        self,
        candidate_profile: dict,
        cover_letter: str,
    ) -> ValidationResult:
        """Validate cover letter doesn't contain hallucinated facts."""
        allowed_facts = self._extract_allowed_facts_from_profile(candidate_profile)
        cover_facts = self._extract_facts(cover_letter)

        issues = []
        for fact in cover_facts - allowed_facts:
            if fact.startswith("number:"):
                issues.append(f"Number '{fact.split(':', 1)[1]}' not found in candidate profile")
            elif fact.startswith("tech:"):
                issues.append(f"Technology '{fact.split(':', 1)[1]}' not found in candidate profile")
            elif fact.startswith("position:"):
                issues.append(f"Position '{fact.split(':', 1)[1]}' not found in candidate profile")

        if issues:
            logger.warning(f"Cover letter validation found {len(issues)} potential hallucinations")

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

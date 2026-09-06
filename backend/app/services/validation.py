"""Anti-hallucination validation for AI-generated content."""

import re
from dataclasses import dataclass, field

from app.core.logging import get_logger

logger = get_logger(__name__)

_EXPLICIT_CLAIM_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "company": (
        re.compile(
            r"\bworked\s+(?:at|for)\s+(.+?)(?=\s+as\b|[.!?\n]|$)",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bработал[аи]?\s+(?:в|на)\s+(.+?)(?=\s+как\b|[.!?\n]|$)",
            re.IGNORECASE,
        ),
    ),
    "project": (
        re.compile(r"\bproject\s*[:—-]?\s*(.+?)(?=[.!?\n]|$)", re.IGNORECASE),
        re.compile(r"\bпроект\s*[:—-]?\s*(.+?)(?=[.!?\n]|$)", re.IGNORECASE),
    ),
    "certification": (
        re.compile(
            r"\bcertification\s*[:—-]?\s*(.+?)(?=[.!?\n]|$)",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bсертификат\s*[:—-]?\s*(.+?)(?=[.!?\n]|$)",
            re.IGNORECASE,
        ),
    ),
}


def _normalize_claim(value: object) -> str:
    """Normalize an explicitly stated entity for exact source-of-truth comparison."""
    return " ".join(str(value).strip().lower().split())


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
            pattern = rf"(?<!\w){re.escape(tech)}(?!\w)"
            if re.search(pattern, text_lower):
                facts.add(f"tech:{tech}")

        for pos in self.POSITION_KEYWORDS:
            if re.search(rf"(?<!\w){re.escape(pos)}(?!\w)", text_lower):
                facts.add(f"position:{pos}")

        for claim_type, patterns in _EXPLICIT_CLAIM_PATTERNS.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    value = _normalize_claim(match.group(1))
                    if value:
                        facts.add(f"{claim_type}:{value}")

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

                    for key in ("institution", "university", "school"):
                        value = _normalize_claim(edu.get(key, ""))
                        if value:
                            allowed.add(f"education:{value}")

        for entry in profile.get("experience", []) or []:
            if not isinstance(entry, dict):
                continue
            company = _normalize_claim(entry.get("company", ""))
            if company:
                allowed.add(f"company:{company}")
            title = _normalize_claim(entry.get("title", ""))
            if title:
                allowed.add(f"position:{title}")

        for project in profile.get("projects", []) or []:
            if not isinstance(project, dict):
                continue
            name = _normalize_claim(project.get("name", ""))
            if name:
                allowed.add(f"project:{name}")

        for certification in profile.get("certifications", []) or []:
            if not isinstance(certification, dict):
                continue
            name = _normalize_claim(certification.get("name", ""))
            if name:
                allowed.add(f"certification:{name}")

        return allowed

    def validate_resume(
        self,
        original_resume: str,
        adapted_resume: str,
        allowed_skills: list[str] | None = None,
        candidate_profile: dict | None = None,
    ) -> ValidationResult:
        """Validate adapted resume doesn't contain unsupported facts.

        The original resume remains the primary evidence source.  A structured
        candidate profile may additionally authorize facts that are stored in
        the profile but were omitted from the particular source document.
        This keeps rewriting useful while preserving the source-of-truth
        boundary: profile facts are allowed, arbitrary generated facts are not.
        """
        original_facts = self._extract_facts(original_resume)
        adapted_facts = self._extract_facts(adapted_resume)
        allowed_facts = set(original_facts)

        if candidate_profile:
            allowed_facts.update(self._extract_allowed_facts_from_profile(candidate_profile))

        if allowed_skills:
            for skill in allowed_skills:
                allowed_facts.add(f"tech:{skill.lower()}")

        issues = []
        for fact in adapted_facts - allowed_facts:
            if fact.startswith("number:"):
                issues.append(f"Number '{fact.split(':', 1)[1]}' not found in original resume")
            elif fact.startswith("tech:"):
                issues.append(f"Technology '{fact.split(':', 1)[1]}' not found in original resume")
            elif fact.startswith("position:"):
                issues.append(f"Position '{fact.split(':', 1)[1]}' not found in original resume")
            elif fact.startswith("company:"):
                issues.append(f"Company '{fact.split(':', 1)[1]}' is not supported")
            elif fact.startswith("project:"):
                issues.append(f"Project '{fact.split(':', 1)[1]}' is not supported")
            elif fact.startswith("certification:"):
                issues.append(f"Certification '{fact.split(':', 1)[1]}' is not supported")

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
            elif fact.startswith("company:"):
                issues.append(f"Company '{fact.split(':', 1)[1]}' is not supported")
            elif fact.startswith("project:"):
                issues.append(f"Project '{fact.split(':', 1)[1]}' is not supported")
            elif fact.startswith("certification:"):
                issues.append(f"Certification '{fact.split(':', 1)[1]}' is not supported")

        if issues:
            logger.warning(f"Cover letter validation found {len(issues)} potential hallucinations")

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

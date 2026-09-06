"""Deterministic resume document parsing (no LLM).

Turns raw resume text into a structured ``ResumeDocument``: sections,
experience entries with bullets, education blocks, detected contacts and dates.

This is the foundation for every other analyzer (ATS, structure, content,
experience, bullet). It is intentionally conservative: it only records what is
literally present in the text, never inferring missing facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Canonical section key -> regexes that identify a header line (ru + en).
_SECTION_PATTERNS: dict[str, re.Pattern] = {
    "contact": re.compile(
        r"^(контакты|контактная информация|контактные данные)\b", re.IGNORECASE
    ),
    "summary": re.compile(
        r"^(обо мне|о себе|профиль|саммари|summary|profile|about me|objective)\b",
        re.IGNORECASE,
    ),
    "experience": re.compile(
        r"^(опыт работы|опыт|места работы|трудовой опыт|опыт трудоустройства|"
        r"experience|work experience|employment|professional experience)\b",
        re.IGNORECASE,
    ),
    "education": re.compile(
        r"^(образование|учеба|обучение|вуз|образование и курсы|education|academic)\b",
        re.IGNORECASE,
    ),
    "skills": re.compile(
        r"^(навыки|ключевые навыки|навыки и технологии|технологии|стек|"
        r"skills|key skills|technical skills|core competencies)\b",
        re.IGNORECASE,
    ),
    "projects": re.compile(r"^(проекты|портфолио|projects|portfolio)\b", re.IGNORECASE),
    "languages": re.compile(
        r"^(языки|знание языков|владение языками|иностранные языки|languages)\b",
        re.IGNORECASE,
    ),
    "certifications": re.compile(
        r"^(сертификаты|сертификации|курсы|дополнительное образование|"
        r"certifications|certificates|courses)\b",
        re.IGNORECASE,
    ),
}

_YEAR_RANGE_RE = re.compile(
    r"\b(?:(?:[A-Za-zА-Яа-яЁё]+)\s+)?((?:19|20)\d{2})\s*[-–—]\s*"
    r"(?:(?:[A-Za-zА-Яа-яЁё]+)\s+)?((?:19|20)\d{2}|present|н\.?\s*в\.?|"
    r"наст(?:оящее)?\s*(?:время)?|по настоящее время|сейчас)\b",
    re.IGNORECASE,
)

# Russian months for date parsing.
_MONTHS_RE = re.compile(
    r"(янв(?:арь)?|фев(?:раль)?|мар(?:т)?|апр(?:ель)?|ма[йя]|июн(?:ь)?|"
    r"июл(?:ь)?|авг(?:уст)?|сен(?:тябрь)?|окт(?:ябрь)?|ноя(?:брь)?|дек(?:абрь)?)",
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{8,}\d")
_URL_RE = re.compile(r"https?://[^\s]+|(?:t\.me|github\.com|linkedin\.com)/[^\s]+")

_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-•*▪·–—]|\d+[.)])\s+")


@dataclass
class ParsedSection:
    """A detected resume section."""

    key: str
    title: str
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass
class ExperienceEntry:
    """One parsed work-experience entry."""

    title: str
    company: str | None = None
    period: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    bullets: list[str] = field(default_factory=list)
    description_lines: list[str] = field(default_factory=list)

    @property
    def all_text(self) -> str:
        return "\n".join([self.title, self.company or ""] + self.bullets + self.description_lines)


@dataclass
class EducationBlock:
    """One parsed education entry."""

    institution: str
    degree: str | None = None
    period: str | None = None
    year: int | None = None


@dataclass
class ResumeDocument:
    """Structured representation of a resume text."""

    raw_text: str
    sections: dict[str, ParsedSection] = field(default_factory=dict)
    preamble_lines: list[str] = field(default_factory=list)
    experience: list[ExperienceEntry] = field(default_factory=list)
    education: list[EducationBlock] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    dates_found: list[str] = field(default_factory=list)
    total_lines: int = 0
    total_words: int = 0

    @property
    def has_experience(self) -> bool:
        return bool(self.experience)

    @property
    def has_education(self) -> bool:
        return bool(self.education)

    @property
    def section_keys(self) -> set[str]:
        return set(self.sections)

    def section_text(self, key: str) -> str:
        sec = self.sections.get(key)
        return sec.text if sec else ""

    def all_bullets(self) -> list[str]:
        bullets: list[str] = []
        for entry in self.experience:
            bullets.extend(entry.bullets)
        return bullets


# ----------------------------------------------------------------------------
# Section splitting.
# ----------------------------------------------------------------------------


def _match_section_header(line: str) -> str | None:
    """Return the canonical section key if this line is a section header."""
    stripped = line.strip().rstrip(":").strip()
    if not stripped or len(stripped) > 60:
        return None
    for key, pattern in _SECTION_PATTERNS.items():
        if pattern.match(stripped):
            return key
    return None


def _split_sections(lines: list[str]) -> tuple[list[str], dict[str, ParsedSection]]:
    """Split the resume into (preamble, sections).

    Lines before the first recognized header belong to the preamble (name,
    contact block, headline). Each header opens a new section; subsequent lines
    accumulate until the next header.
    """
    preamble: list[str] = []
    sections: dict[str, ParsedSection] = {}
    current_key: str | None = None

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            if current_key:
                sections[current_key].lines.append("")
            continue

        header = _match_section_header(line)
        if header:
            current_key = header
            if header not in sections:
                sections[header] = ParsedSection(key=header, title=line.strip())
            continue

        if current_key is None:
            preamble.append(line)
        else:
            sections[current_key].lines.append(line)

    for sec in sections.values():
        while sec.lines and not sec.lines[-1].strip():
            sec.lines.pop()

    return preamble, sections


# ----------------------------------------------------------------------------
# Experience & Education parsing helpers.
# ----------------------------------------------------------------------------


def _parse_experience(lines: list[str]) -> list[ExperienceEntry]:
    """Parse experience section lines into structured entries."""
    entries: list[ExperienceEntry] = []
    current: ExperienceEntry | None = None
    after_blank = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            after_blank = True
            continue

        date_match = _YEAR_RANGE_RE.search(stripped)
        if date_match:
            if current is None:
                current = ExperienceEntry(title="Unknown position")
            current.period = stripped
            current.start_year = int(date_match.group(1))
            end_str = date_match.group(2).lower()
            if not re.search(r"present|н\.?\s*в\.?|наст|сейчас", end_str):
                current.end_year = int(end_str)
            after_blank = False
            continue

        if _BULLET_PREFIX_RE.match(line):
            bullet_text = _BULLET_PREFIX_RE.sub("", line).strip()
            if current:
                current.bullets.append(bullet_text)
            after_blank = False
            continue

        if current is None:
            current = ExperienceEntry(title=stripped)
        elif current.company is None and current.period is None and not current.bullets:
            current.company = stripped
        elif after_blank and (current.period or current.bullets or current.description_lines):
            if current.title:
                entries.append(current)
            current = ExperienceEntry(title=stripped)
        else:
            current.description_lines.append(stripped)
        after_blank = False

    if current and current.title:
        entries.append(current)

    return entries


def _parse_education(lines: list[str]) -> list[EducationBlock]:
    """Parse education section lines into blocks."""
    blocks: list[EducationBlock] = []
    current: EducationBlock | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check for date/year.
        year_match = re.search(r"\b(19|20)\d{2}\b", stripped)
        if year_match and current:
            current.period = stripped
            try:
                current.year = int(year_match.group())
            except (ValueError, IndexError):
                pass
            continue

        # New entry starts with non-date, non-bullet.
        if not _BULLET_PREFIX_RE.match(line):
            if current:
                blocks.append(current)
            current = EducationBlock(institution=stripped)
            continue

        # Bullet = degree.
        if _BULLET_PREFIX_RE.match(line) and current:
            degree_text = _BULLET_PREFIX_RE.sub("", line).strip()
            current.degree = degree_text

    if current:
        blocks.append(current)

    return blocks


# ----------------------------------------------------------------------------
# Main entry point.
# ----------------------------------------------------------------------------


def parse_resume_document(text: str) -> ResumeDocument:
    """Parse a raw resume text into a structured ResumeDocument.

    This is the main public API of the document parsing module.

    Args:
        text: Raw resume text (can contain multiple lines, section headers,
              bullet points, etc.).

    Returns:
        A ``ResumeDocument`` containing all parsed information.
    """
    lines = text.split("\n")
    preamble, sections = _split_sections(lines)

    # Build experience entries from the experience section.
    experience: list[ExperienceEntry] = []
    exp_section = sections.get("experience")
    if exp_section:
        experience = _parse_experience(exp_section.lines)

    # Build education entries.
    education: list[EducationBlock] = []
    edu_section = sections.get("education")
    if edu_section:
        education = _parse_education(edu_section.lines)

    # Extract contact info from preamble.
    emails = _EMAIL_RE.findall(text)
    phones = [
        phone
        for phone in _PHONE_RE.findall(text)
        if not _YEAR_RANGE_RE.fullmatch(phone.strip())
    ]
    urls = _URL_RE.findall(text)
    dates_found = [match.group(0) for match in _YEAR_RANGE_RE.finditer(text)]

    # Count words (crude estimate).
    total_words = sum(len(line.split()) for line in lines)

    return ResumeDocument(
        raw_text=text,
        sections=sections,
        preamble_lines=preamble,
        experience=experience,
        education=education,
        emails=emails,
        phones=phones,
        urls=urls,
        dates_found=dates_found,
        total_lines=len(lines),
        total_words=total_words,
    )


__all__ = [
    "ParsedSection",
    "ExperienceEntry",
    "EducationBlock",
    "ResumeDocument",
    "parse_resume_document",
]

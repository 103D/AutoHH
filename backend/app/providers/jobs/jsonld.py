"""Shared JSON-LD helpers for job board scrapers.

Many job boards (Habr Career, Zarplata, etc.) embed schema.org JobPosting
structured data in their pages. Parsing these <script type="application/ld+json">
blocks is far more stable than scraping raw HTML.
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_SCRIPT_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_ENTITY_RE = re.compile(r"&[a-z#0-9]+;")


def strip_html(html: str) -> str:
    """Strip HTML tags and decode basic entities."""
    text = _TAG_RE.sub(" ", html or "")
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    text = _ENTITY_RE.sub(" ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def extract_jobposting_blocks(html: str) -> list[dict[str, Any]]:
    """Extract schema.org JobPosting dicts from JSON-LD blocks in an HTML page.

    Returns an empty list (with a warning) when the page structure changed
    and no structured data is found.
    """
    postings: list[dict[str, Any]] = []
    for match in _SCRIPT_RE.finditer(html or ""):
        try:
            data = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            logger.warning("Skipping malformed JSON-LD block")
            continue

        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                postings.append(item)
            elif isinstance(item, dict) and isinstance(item.get("@graph"), list):
                for graph_item in item["@graph"]:
                    if isinstance(graph_item, dict) and graph_item.get("@type") == "JobPosting":
                        postings.append(graph_item)

    if not postings:
        logger.warning("No JobPosting JSON-LD blocks found on the page")
    return postings


def stable_external_id(url: str) -> str:
    """Derive a stable external id from a vacancy URL when the page has no id."""
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:12]


_CURRENCY_MAP = {
    "rur": "RUB",
    "rub": "RUB",
    "kzt": "KZT",
    "usd": "USD",
    "eur": "EUR",
}

_EMPLOYMENT_MAP = {
    "full_time": "full_time",
    "part_time": "part_time",
    "contract": "contract",
    "contractor": "contract",
    "temporary": "part_time",
    "internship": "internship",
    "полная занятость": "full_time",
    "неполная занятость": "part_time",
    "полный рабочий день": "full_time",
    "неполный рабочий день": "part_time",
}

_WORK_FORMAT_MAP = {
    "remote": "remote",
    "telecommute": "remote",
    "удалённая работа": "remote",
    "удаленная работа": "remote",
    "hybrid": "hybrid",
    "гибрид": "hybrid",
    "office": "office",
    "on_site": "office",
    "на территории работодателя": "office",
    "в офисе": "office",
}


def jobposting_to_rawjob(posting: dict[str, Any], base_url: str) -> dict[str, Any]:
    """Normalize a schema.org JobPosting dict into RawJob-compatible kwargs.

    Returns the raw kwargs dict (not a RawJob instance) so callers can
    override fields before validation.
    """
    org = posting.get("hiringOrganization") or {}
    if isinstance(org, list):
        org = org[0] if org else {}

    location = None
    job_location = posting.get("jobLocation") or {}
    if isinstance(job_location, list):
        job_location = job_location[0] if job_location else {}
    if isinstance(job_location, dict):
        address = job_location.get("address") or {}
        if isinstance(address, list):
            address = address[0] if address else {}
        if isinstance(address, dict):
            location = address.get("addressLocality") or address.get("addressRegion")

    url_value = posting.get("@id") or posting.get("url") or posting.get("sameAs") or ""
    if url_value and str(url_value).startswith("/"):
        url_value = f"{base_url.rstrip('/')}{url_value}"

    identifier = posting.get("identifier") or {}
    if isinstance(identifier, dict):
        external_id = str(identifier.get("value") or "") or stable_external_id(str(url_value))
    else:
        external_id = str(identifier or "") or stable_external_id(str(url_value))

    # Salary: baseSalary.value with minValue/maxValue (or a single "value")
    salary_min = None
    salary_max = None
    currency = None
    salary = posting.get("baseSalary") or {}
    if isinstance(salary, list):
        salary = salary[0] if salary else {}
    value = salary.get("value") or {} if isinstance(salary, dict) else {}
    if isinstance(value, dict):
        salary_min = value.get("minValue") or value.get("value")
        salary_max = value.get("maxValue")
        unit = value.get("unitText")
        if unit:
            currency = _CURRENCY_MAP.get(str(unit).lower(), str(unit).upper())

    employment_raw = str(posting.get("employmentType") or "")
    employment_type = _EMPLOYMENT_MAP.get(employment_raw.lower().replace(" ", "_"))
    if employment_type is None and employment_raw:
        employment_type = _EMPLOYMENT_MAP.get(employment_raw.lower())
    work_format = _WORK_FORMAT_MAP.get(str(posting.get("applicantLocationRequirements") or {}).lower())
    if not work_format:
        remote_type = posting.get("jobLocationType") or ""
        work_format = "remote" if str(remote_type).upper() == "TELECOMMUTE" else None

    published_at = None
    date_posted = posting.get("datePosted")
    if date_posted:
        try:
            published_at = datetime.fromisoformat(str(date_posted).replace("Z", "+00:00"))
        except ValueError:
            pass

    return {
        "external_id": external_id,
        "title": str(posting.get("title") or posting.get("name") or "Untitled"),
        "company": str(org.get("name") or "Unknown"),
        "description": strip_html(str(posting.get("description") or "")) or " ",
        "url": str(url_value),
        "location": location,
        "salary_min": int(salary_min) if salary_min else None,
        "salary_max": int(salary_max) if salary_max else None,
        "currency": currency,
        "employment_type": employment_type,
        "work_format": work_format,
        "published_at": published_at,
        "raw_data": posting,
    }


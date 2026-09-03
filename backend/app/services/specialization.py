"""Deterministic multi-label job specialization classifier (task spec #11).

Classifies vacancies into analytics specializations using title (strong
signal), description and skills — never the title alone. Fully
deterministic (no LLM), cheap enough to run at ingestion time.

Multi-label: a vacancy may belong to several specializations at once
(e.g. "Data Analyst for retail" -> DATA_ANALYST + RETAIL_COMMERCIAL_ANALYST).
"""

from app.services.skill_taxonomy import normalize_skill


class Specialization:
    """Analytics specializations supported by resume profiles."""

    DATA_ANALYST = "DATA_ANALYST"
    BI_ANALYST = "BI_ANALYST"
    PRODUCT_ANALYST = "PRODUCT_ANALYST"
    RETAIL_COMMERCIAL_ANALYST = "RETAIL_COMMERCIAL_ANALYST"

    ALL: list[str] = [
        DATA_ANALYST,
        BI_ANALYST,
        PRODUCT_ANALYST,
        RETAIL_COMMERCIAL_ANALYST,
    ]


# A single title hit assigns the label.
TITLE_KEYWORDS: dict[str, list[str]] = {
    Specialization.DATA_ANALYST: [
        "data analyst",
        "data analytics",
        "аналитик данных",
        "аналитик data",
        "data-аналитик",
    ],
    Specialization.BI_ANALYST: [
        "bi analyst",
        "bi-аналитик",
        "bi аналитик",
        "business intelligence",
        "power bi",
        "tableau",
    ],
    Specialization.PRODUCT_ANALYST: [
        "product analyst",
        "product data analyst",
        "продуктовый аналитик",
        "продукт-аналитик",
    ],
    Specialization.RETAIL_COMMERCIAL_ANALYST: [
        "retail analyst",
        "commercial analyst",
        "ритейл-аналитик",
        "ритейл аналитик",
        "коммерческий аналитик",
        "категорийный аналитик",
        "аналитик розницы",
    ],
}

# Body-only hits must reach BODY_MIN_SCORE to assign a label.
BODY_KEYWORDS: dict[str, list[str]] = {
    Specialization.DATA_ANALYST: [
        "sql",
        "python",
        "pandas",
        "numpy",
        "statistics",
        "статистик",
        "анализ данных",
        "аналитика данных",
        "data analysis",
        "working with data",
        "аналитических задач",
        "датасет",
    ],
    Specialization.BI_ANALYST: [
        "power bi",
        "powerbi",
        "tableau",
        "dax",
        "olap",
        "dashboard",
        "дашборд",
        "дэшборд",
        "reporting",
        "отчетность",
        "отчётность",
        "data visualization",
        "визуализация данных",
        "superset",
        "metabase",
        "looker",
        "qlik",
        " bi ",
        "bi-",
    ],
    Specialization.PRODUCT_ANALYST: [
        "product analytics",
        "продуктовая аналитика",
        "продуктовых метрик",
        "продуктовые метрики",
        "unit-экономика",
        "юнит-экономика",
        "unit economics",
        "retention",
        "конверси",
        "воронк",
        "funnel",
        "a/b test",
        "a/b-тест",
        "ab-тест",
        "product metrics",
        "churn",
        "ltv",
        "hypotesis",
        "гипотез",
    ],
    Specialization.RETAIL_COMMERCIAL_ANALYST: [
        "retail",
        "ритейл",
        "розниц",
        "рознич",
        "fmcg",
        "торговл",
        "мерчандайз",
        "ассортимент",
        "inventory",
        "товарны",
        "запасов",
        "продаж",
        "коммерческ",
        "планограмм",
        "сезонность",
        "план-факт",
        "товарооборот",
        "оборачиваемость",
    ],
}

TITLE_WEIGHT = 3
BODY_WEIGHT = 1
BODY_MIN_SCORE = 3  # body-only hits required to assign a label


def classify_job(
    title: str,
    description: str = "",
    skills: list[str] | None = None,
) -> list[str]:
    """Classify a vacancy into specializations (multi-label).

    Returns labels sorted by match strength (strongest first).
    An empty list means the vacancy could not be classified.
    """
    title_text = (title or "").lower()
    skill_text = " ".join(
        normalize_skill(s) for s in (skills or []) if s
    ).lower()
    body_text = f"{description or ''} {skill_text}".lower()

    scored: list[tuple[float, str]] = []
    for spec in Specialization.ALL:
        title_score = sum(
            TITLE_WEIGHT
            for kw in TITLE_KEYWORDS[spec]
            if kw in title_text
        )
        body_score = sum(
            BODY_WEIGHT
            for kw in BODY_KEYWORDS[spec]
            if kw in body_text
        )
        total = title_score + body_score
        # Title hit alone is a strong signal; body needs several hits.
        if title_score > 0 or body_score >= BODY_MIN_SCORE:
            scored.append((total, spec))

    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [spec for _, spec in scored]

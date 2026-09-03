"""Skill taxonomy: canonical skill names with a conservative alias layer.

Rules (see task spec #14):
- "PostgreSQL", "postgres", "Postgres" are one skill (PostgreSQL).
- "Power BI", "PowerBI", "Microsoft Power BI" are one skill (Power BI).
- Technologies that merely look similar are NEVER merged:
  PostgreSQL != MySQL, Power BI != Tableau, DAX != SQL.

The alias layer is intentionally small: an alias is added only where the
equivalence is unambiguous. Unknown skills pass through unchanged.
"""

# Lowercase canonical key -> canonical display form.
CANONICAL_SKILLS: dict[str, str] = {
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "sql": "SQL",
    "dax": "DAX",
    "python": "Python",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "java": "Java",
    "kubernetes": "Kubernetes",
    "docker": "Docker",
    "git": "Git",
    "excel": "Excel",
    "power bi": "Power BI",
    "power query": "Power Query",
    "power pivot": "PowerPivot",
    "tableau": "Tableau",
    "looker": "Looker",
    "qlik": "Qlik",
    "superset": "Apache Superset",
    "metabase": "Metabase",
    "business intelligence": "Business Intelligence",
    "machine learning": "Machine Learning",
    "apache spark": "Apache Spark",
    "apache airflow": "Apache Airflow",
    "apache kafka": "Apache Kafka",
    "clickhouse": "ClickHouse",
    "greenplum": "Greenplum",
    "hadoop": "Hadoop",
    "1c": "1C",
}

# Lowercase alias -> canonical key. Only unambiguous equivalences.
SKILL_ALIASES: dict[str, str] = {
    # PostgreSQL (PostgreSQL != MySQL: no cross-aliases ever)
    "postgres": "postgresql",
    "postgre": "postgresql",
    "постгрес": "postgresql",
    "pgsql": "postgresql",
    "pg": "postgresql",
    # Power BI (Power BI != Tableau: no cross-aliases)
    "powerbi": "power bi",
    "microsoft power bi": "power bi",
    "ms power bi": "power bi",
    "пауэр би": "power bi",
    # Excel
    "microsoft excel": "excel",
    "ms excel": "excel",
    "эксель": "excel",
    # Power Query / PowerPivot (distinct DAX-adjacent tools, kept separate)
    "powerquery": "power query",
    "powerpivot": "power pivot",
    # DAX (DAX != SQL: no cross-aliases)
    "dax formulas": "dax",
    # Python
    "python3": "python",
    "питон": "python",
    # JavaScript / TypeScript
    "js": "javascript",
    "ecmascript": "javascript",
    "es6": "javascript",
    "ts": "typescript",
    # Kubernetes
    "k8s": "kubernetes",
    # Business Intelligence ("BI" is only safe with word boundaries, hence
    # it is matched via tokenized text, never via bare substring search)
    "bi": "business intelligence",
    # Machine Learning
    "ml": "machine learning",
    "машинное обучение": "machine learning",
    # Spark / Airflow / Kafka
    "spark": "apache spark",
    "airflow": "apache airflow",
    "kafka": "apache kafka",
}

# canonical key -> list of lowercase aliases (built once at import).
ALIASES_BY_CANONICAL: dict[str, list[str]] = {}
for _alias, _key in SKILL_ALIASES.items():
    ALIASES_BY_CANONICAL.setdefault(_key, []).append(_alias)


def canonical_key(skill: str) -> str:
    """Lowercase canonical key for a skill (identity for unknown skills)."""
    cleaned = str(skill).strip().lower()
    if not cleaned:
        return ""
    return SKILL_ALIASES.get(cleaned, cleaned)


def normalize_skill(skill: str) -> str:
    """Canonical display form of a skill; unknown skills pass through."""
    key = canonical_key(skill)
    if not key:
        return ""
    display = CANONICAL_SKILLS.get(key)
    return display if display else str(skill).strip()


def skill_variants(skill: str) -> set[str]:
    """All lowercase textual variants that should match this skill in free text.

    E.g. for "Power BI" the variants are {"power bi", "powerbi",
    "microsoft power bi", "ms power bi", "пауэр би"}.
    Variants are matched against tokens of the job text, so the bare "bi"
    alias can never false-positive inside words like "mobile".
    """
    key = canonical_key(skill)
    if not key:
        return set()
    variants = {key, *ALIASES_BY_CANONICAL.get(key, [])}
    display = CANONICAL_SKILLS.get(key)
    if display:
        variants.add(display.lower())
    return variants

"""Tests for the skill taxonomy (task spec #14)."""

from app.services.skill_taxonomy import normalize_skill, skill_variants


def test_postgresql_aliases_are_one_skill():
    assert normalize_skill("PostgreSQL") == "PostgreSQL"
    assert normalize_skill("postgres") == "PostgreSQL"
    assert normalize_skill("Postgres") == "PostgreSQL"
    assert normalize_skill("постгрес") == "PostgreSQL"
    assert normalize_skill("pgsql") == "PostgreSQL"


def test_power_bi_aliases_are_one_skill():
    for variant in ("Power BI", "PowerBI", "powerbi", "Microsoft Power BI", "MS Power BI"):
        assert normalize_skill(variant) == "Power BI"


def test_similar_technologies_are_never_merged():
    assert normalize_skill("MySQL") == "MySQL"
    assert normalize_skill("PostgreSQL") != normalize_skill("MySQL")
    assert normalize_skill("Tableau") == "Tableau"
    assert normalize_skill("Power BI") != normalize_skill("Tableau")
    assert normalize_skill("DAX") == "DAX"
    assert normalize_skill("SQL") == "SQL"
    assert normalize_skill("DAX") != normalize_skill("SQL")


def test_unknown_skill_passes_through():
    assert normalize_skill("Cohort Analysis") == "Cohort Analysis"
    assert normalize_skill("  Retail Analytics ") == "Retail Analytics"


def test_known_skill_gets_canonical_display_form():
    assert normalize_skill("k8s") == "Kubernetes"
    assert normalize_skill("ML") == "Machine Learning"
    assert normalize_skill("spark") == "Apache Spark"


def test_skill_variants_cover_aliases():
    variants = skill_variants("Power BI")
    assert {"power bi", "powerbi", "microsoft power bi"} <= variants


def test_bi_alias_does_not_false_positive_in_words():
    # "Mobile" contains "bi" as a substring but is not Business Intelligence:
    # unknown skills pass through and variants are matched token-wise.
    assert normalize_skill("Mobile") == "Mobile"
    assert "mobile" not in skill_variants("Power BI")
    assert "business intelligence" in skill_variants("BI")

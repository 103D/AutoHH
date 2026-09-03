"""Tests for deterministic specialization classification (task spec #11)."""

from app.services.specialization import Specialization, classify_job


def test_title_hit_assigns_data_analyst():
    assert classify_job("Data Analyst", "Мы ищем специалиста.") == [
        Specialization.DATA_ANALYST
    ]


def test_russian_title():
    assert classify_job("Продуктовый аналитик", "Работа с метриками продукта.") == [
        Specialization.PRODUCT_ANALYST
    ]


def test_bi_title():
    assert classify_job("BI Analyst", "Reports and dashboards.") == [
        Specialization.BI_ANALYST
    ]


def test_body_needs_min_hits():
    # One body hit is below the threshold of three.
    assert classify_job("Специалист", "SQL и отчетность.") == []
    three_hits = classify_job(
        "Специалист",
        "Power BI, DAX, построение дашбордов, отчетность.",
    )
    assert three_hits == [Specialization.BI_ANALYST]


def test_multilabel_retail_and_bi():
    labels = classify_job(
        "BI Analyst",
        "Retail сеть. Ассортимент, товарные запасы, план-факт, Power BI, DAX.",
    )
    assert Specialization.BI_ANALYST in labels
    assert Specialization.RETAIL_COMMERCIAL_ANALYST in labels


def test_product_body_classification():
    labels = classify_job(
        "Аналитик",
        "Продуктовая аналитика: воронка, конверсия, юнит-экономика, A/B тесты.",
    )
    assert labels == [Specialization.PRODUCT_ANALYST]


def test_no_classification_for_unrelated_vacancy():
    assert classify_job("Менеджер по продажам", "Холодные звонки, CRM.") == []


def test_skills_contribute_to_body_score():
    labels = classify_job(
        "Аналитик",
        "Аналитика данных.",
        skills=["Power BI", "DAX", "Tableau"],
    )
    assert Specialization.BI_ANALYST in labels


def test_sorted_by_strength():
    labels = classify_job(
        "BI Analyst",
        "Retail сеть: ассортимент, товарные запасы, план-факт, Power BI, DAX, дашборды.",
    )
    # BI has a title hit (stronger), retail only body hits.
    assert labels[0] == Specialization.BI_ANALYST
    assert Specialization.RETAIL_COMMERCIAL_ANALYST in labels

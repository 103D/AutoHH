"""Tests for deterministic threshold suggestions (task specs #18, #32)."""

from types import SimpleNamespace

from app.services.threshold_advisor import ThresholdAdvisor


def _rows():
    return [
        {"bucket": "0-39", "applications": 10, "interviews": 0},
        {"bucket": "40-54", "applications": 8, "interviews": 1},
        {"bucket": "55-69", "applications": 6, "interviews": 3},
        {"bucket": "70-84", "applications": 5, "interviews": 4},
        {"bucket": "85+", "applications": 4, "interviews": 3},
    ]


def test_best_bucket_selected_by_interview_rate():
    suggestion = ThresholdAdvisor().suggest(_rows())

    # 70-84 has the highest rate (4/5 = 80%) with enough applications.
    assert suggestion.best_bucket == "70-84"
    assert suggestion.suggested_min_llm_score == 70
    assert suggestion.data_points == 33


def test_skip_below_is_lower_bound_of_first_bucket_with_interviews():
    suggestion = ThresholdAdvisor().suggest(_rows())

    # 0-39 produced no interviews; the first interview bucket starts at 40.
    assert suggestion.suggested_skip_below == 40
    assert any("No interviews below 40" in i for i in suggestion.insights)


def test_no_data_returns_no_suggestions():
    suggestion = ThresholdAdvisor().suggest([])

    assert suggestion.suggested_min_llm_score is None
    assert suggestion.suggested_skip_below is None
    assert suggestion.best_bucket is None
    assert suggestion.data_points == 0
    assert suggestion.insights  # explanation provided


def test_all_zero_interviews_no_skip_suggestion():
    rows = [{"bucket": "0-39", "applications": 5, "interviews": 0}]

    suggestion = ThresholdAdvisor().suggest(rows)

    assert suggestion.suggested_skip_below is None


def test_interviews_from_the_first_bucket_no_skip_suggestion():
    rows = [
        {"bucket": "0-39", "applications": 5, "interviews": 1},
        {"bucket": "40-54", "applications": 5, "interviews": 2},
    ]

    suggestion = ThresholdAdvisor().suggest(rows)

    assert suggestion.suggested_skip_below is None


def test_sparse_data_marked_provisional():
    advisor = ThresholdAdvisor(min_applications_per_bucket=50)

    suggestion = advisor.suggest(_rows())

    assert any("provisional" in i for i in suggestion.insights)
    # Falls back to all data instead of returning nothing.
    assert suggestion.best_bucket is not None


def test_min_applications_filters_unqualified_buckets():
    advisor = ThresholdAdvisor(min_applications_per_bucket=5)
    rows = [
        {"bucket": "0-39", "applications": 2, "interviews": 2},  # tiny, high rate
        {"bucket": "40-54", "applications": 10, "interviews": 3},
    ]

    suggestion = advisor.suggest(rows)

    # The 2-application bucket must not drive the suggestion.
    assert suggestion.best_bucket == "40-54"
    assert suggestion.suggested_min_llm_score == 40


def test_adapter_accepts_pydantic_like_rows():
    stats = SimpleNamespace(
        score_buckets=[
            SimpleNamespace(bucket="0-39", applications=10, interviews=0),
            SimpleNamespace(bucket="40-54", applications=10, interviews=2),
        ]
    )

    suggestion = ThresholdAdvisor().suggest_from_response(stats)

    assert suggestion.best_bucket == "40-54"
    assert suggestion.suggested_skip_below == 40


def test_adapter_accepts_plain_dict_rows():
    stats = {
        "score_buckets": [
            {"bucket": "55-69", "total": 4, "interviews": 1},
            {"bucket": "70-84", "total": 6, "interviews": 2},
        ]
    }

    suggestion = ThresholdAdvisor().suggest_from_response(stats)

    assert suggestion.best_bucket == "70-84"
    assert suggestion.data_points == 10

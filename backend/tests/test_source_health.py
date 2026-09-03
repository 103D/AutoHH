"""Tests for source health / auto-disable logic."""

from types import SimpleNamespace

from app.services.source_health import on_source_failure, on_source_success


def _make_source(consecutive_errors: int = 0, enabled: bool = True):
    return SimpleNamespace(
        enabled=enabled,
        consecutive_errors=consecutive_errors,
        last_error=None,
        last_success_at=None,
    )


def test_success_resets_errors():
    source = _make_source(consecutive_errors=3)
    on_source_success(source)
    assert source.consecutive_errors == 0
    assert source.last_error is None
    assert source.last_success_at is not None


def test_failure_increments_without_disabling():
    source = _make_source()
    disabled = on_source_failure(source, "boom", max_consecutive=5)
    assert disabled is False
    assert source.consecutive_errors == 1
    assert source.enabled is True
    assert source.last_error == "boom"


def test_failure_disables_after_threshold():
    source = _make_source(consecutive_errors=4)
    disabled = on_source_failure(source, "boom", max_consecutive=5)
    assert disabled is True
    assert source.enabled is False
    assert source.consecutive_errors == 5
    assert "Disabled after 5 consecutive failures" in source.last_error


def test_first_failure_with_default_threshold_keeps_source_enabled():
    source = _make_source()
    disabled = on_source_failure(source, "boom")
    assert disabled is False  # settings.max_consecutive_source_errors >= 1
    assert source.consecutive_errors == 1

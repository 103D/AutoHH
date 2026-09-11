"""Tests for AutonomyMode parsing and permissions."""

from app.hermes.modes import AutonomyMode


class TestAutonomyMode:
    def test_from_str_read_only(self):
        assert AutonomyMode.from_str("READ_ONLY") == AutonomyMode.READ_ONLY

    def test_from_str_assisted(self):
        assert AutonomyMode.from_str("ASSISTED") == AutonomyMode.ASSISTED

    def test_from_str_autonomous(self):
        assert AutonomyMode.from_str("AUTONOMOUS") == AutonomyMode.AUTONOMOUS

    def test_from_str_case_insensitive(self):
        assert AutonomyMode.from_str("read_only") == AutonomyMode.READ_ONLY
        assert AutonomyMode.from_str("Assisted") == AutonomyMode.ASSISTED

    def test_from_str_empty_defaults_to_read_only(self):
        assert AutonomyMode.from_str("") == AutonomyMode.READ_ONLY

    def test_from_str_invalid_defaults_to_read_only(self):
        assert AutonomyMode.from_str("INVALID") == AutonomyMode.READ_ONLY

    def test_allows_mutation_read_only(self):
        assert AutonomyMode.READ_ONLY.allows_mutation() is False

    def test_allows_mutation_assisted(self):
        assert AutonomyMode.ASSISTED.allows_mutation() is True

    def test_allows_mutation_autonomous(self):
        assert AutonomyMode.AUTONOMOUS.allows_mutation() is True

    def test_allows_autonomous_apply_read_only(self):
        assert AutonomyMode.READ_ONLY.allows_autonomous_apply() is False

    def test_allows_autonomous_apply_assisted(self):
        assert AutonomyMode.ASSISTED.allows_autonomous_apply() is False

    def test_allows_autonomous_apply_autonomous(self):
        assert AutonomyMode.AUTONOMOUS.allows_autonomous_apply() is True

    def test_requires_approval_read_only(self):
        assert AutonomyMode.READ_ONLY.requires_approval() is True

    def test_requires_approval_assisted(self):
        assert AutonomyMode.ASSISTED.requires_approval() is True

    def test_requires_approval_autonomous(self):
        assert AutonomyMode.AUTONOMOUS.requires_approval() is False

    def test_enum_values(self):
        assert AutonomyMode.READ_ONLY.value == "READ_ONLY"
        assert AutonomyMode.ASSISTED.value == "ASSISTED"
        assert AutonomyMode.AUTONOMOUS.value == "AUTONOMOUS"


class TestAutonomyModeValueSemantics:
    def test_str_enum_comparison(self):
        mode = AutonomyMode.from_str("AUTONOMOUS")
        assert mode == "AUTONOMOUS"
        assert mode == AutonomyMode.AUTONOMOUS

"""Autonomy modes for Hermes orchestration.

Determines what actions Hermes is allowed to take on the candidate's behalf:

- READ_ONLY: only read operations (search, get, analyze). No writes, no applies.
- ASSISTED: read + AI analysis + recommendations, but every mutating action
  (create application, update status, adapt resume) requires explicit approval.
- AUTONOMOUS: Hermes can execute approved action types automatically, but only
  when the job satisfies the user's stated policy (min_score, salary, location,
  specialization, experience gap, etc.).
"""

from enum import StrEnum


class AutonomyMode(StrEnum):
    """Autonomy level controlling Hermes action permissions."""

    READ_ONLY = "READ_ONLY"
    ASSISTED = "ASSISTED"
    AUTONOMOUS = "AUTONOMOUS"

    @classmethod
    def from_str(cls, value: str) -> "AutonomyMode":
        """Parse a mode from a string, case-insensitive."""
        if not value:
            return cls.READ_ONLY
        try:
            return cls(value.upper())
        except ValueError:
            return cls.READ_ONLY

    def allows_mutation(self) -> bool:
        """Whether this mode permits any data-modifying actions."""
        return self in (AutonomyMode.AUTONOMOUS, AutonomyMode.ASSISTED)

    def allows_autonomous_apply(self) -> bool:
        """Whether this mode permits automatic application submission."""
        return self == AutonomyMode.AUTONOMOUS

    def requires_approval(self) -> bool:
        """Whether actions require manual approval (ASSISTED and below)."""
        return self != AutonomyMode.AUTONOMOUS

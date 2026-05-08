"""Structured output models for agent findings.

The agent emits Findings as JSON conforming to these schemas. Using
Pydantic instead of regex-parsed strings means we get validation,
type-safety, and self-documenting field meanings.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Finding(BaseModel):
    """A single finding from one investigation cycle."""

    severity: Severity = Field(
        description="How urgent this is. Most findings should be 'info' "
        "or 'low'; reserve 'high'/'critical' for clear malicious behavior."
    )
    summary: str = Field(
        description="One-sentence headline. Should be specific.",
        max_length=200,
    )
    affected_pod: str | None = Field(
        default=None,
        description="The pod where suspicious activity was observed.",
    )
    suspicious_binary: str | None = Field(
        default=None, description="The binary path that triggered the concern."
    )
    parent_chain: list[str] = Field(
        default_factory=list,
        description="Process ancestry leading to the suspicious exec.",
    )
    reasoning: str = Field(
        description="Why this is suspicious (or why it's clean). "
        "Should reference specific data points the agent saw."
    )
    suggested_action: str | None = Field(
        default=None,
        description="What an SRE/security analyst should do next. "
        "Investigation-only for now — no actual remediation.",
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CleanRun(BaseModel):
    """Returned when the agent finds nothing suspicious."""

    summary: str = "No suspicious activity detected."
    reasoning: str
    queries_run: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)

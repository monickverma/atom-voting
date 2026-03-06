"""
Atom Voting — domain models.
Pure Pydantic models with no framework or database dependencies.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class VoteStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class Poll(BaseModel):
    """Represents a voting poll."""

    id: str
    title: str
    options: list[str] = Field(..., min_length=2)
    closes_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_open(self) -> bool:
        """Return True if the poll is still accepting votes."""
        return datetime.now(timezone.utc) < self.closes_at

    @property
    def status(self) -> VoteStatus:
        return VoteStatus.OPEN if self.is_open() else VoteStatus.CLOSED


class CastVoteRequest(BaseModel):
    """Incoming request to cast a vote."""

    choice: str


class Vote(BaseModel):
    """A single recorded vote."""

    poll_id: str
    voter_id: str
    choice: str
    cast_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VoteResult(BaseModel):
    """Result for a single option in a poll."""

    option: str
    votes: int
    percentage: float


class PollResults(BaseModel):
    """Aggregated results for a poll."""

    poll_id: str
    total_votes: int
    results: list[VoteResult]

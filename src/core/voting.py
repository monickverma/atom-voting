"""
Atom Voting — core domain logic.

Pure functions with no framework or I/O imports.
Tests can import and call these directly without any running server or database.
"""
from __future__ import annotations

from src.models.vote import Poll, PollResults, Vote, VoteResult


class VotingError(Exception):
    """Base class for voting domain errors."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class PollClosedError(VotingError):
    def __init__(self) -> None:
        super().__init__("POLL_CLOSED", "Voting period has ended.")


class InvalidChoiceError(VotingError):
    def __init__(self, choice: str, options: list[str]) -> None:
        super().__init__(
            "INVALID_CHOICE",
            f"'{choice}' is not a valid option. Choose from: {options}",
        )


class DuplicateVoteError(VotingError):
    def __init__(self) -> None:
        super().__init__("VOTE_ALREADY_CAST", "You have already voted in this poll.")


def validate_vote(poll: Poll, voter_id: str, choice: str, existing_votes: list[Vote]) -> None:
    """
    Validate that a vote can be cast.

    Raises VotingError subclass if the vote is invalid.
    This is pure domain logic — no database, no HTTP.
    """
    if not poll.is_open():
        raise PollClosedError()

    if choice not in poll.options:
        raise InvalidChoiceError(choice, poll.options)

    already_voted = any(v.voter_id == voter_id and v.poll_id == poll.id for v in existing_votes)
    if already_voted:
        raise DuplicateVoteError()


def tally_votes(poll: Poll, votes: list[Vote]) -> PollResults:
    """
    Compute the vote tally for a poll.

    Pure function — given the same inputs, always returns the same output.
    """
    counts: dict[str, int] = {option: 0 for option in poll.options}

    for vote in votes:
        if vote.choice in counts:
            counts[vote.choice] += 1

    total = sum(counts.values())

    results = [
        VoteResult(
            option=option,
            votes=count,
            percentage=round((count / total * 100), 1) if total > 0 else 0.0,
        )
        for option, count in counts.items()
    ]

    return PollResults(
        poll_id=poll.id,
        total_votes=total,
        results=results,
    )

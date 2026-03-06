"""
Atom Voting — vote service.

Orchestrates use cases using core domain logic.
This layer owns the "what to do" — it calls core for domain decisions
and will call database/cache adapters for persistence (to be wired later).
"""
from __future__ import annotations

from src.core.voting import tally_votes, validate_vote
from src.models.vote import CastVoteRequest, Poll, PollResults, Vote

# In-memory store for hackathon demo. Replace with a real repository adapter.
_polls: dict[str, Poll] = {}
_votes: list[Vote] = []


def get_poll(poll_id: str) -> Poll | None:
    return _polls.get(poll_id)


def create_poll(poll: Poll) -> Poll:
    _polls[poll.id] = poll
    return poll


def cast_vote(poll: Poll, voter_id: str, request: CastVoteRequest) -> Vote:
    """
    Cast a vote in a poll.

    Delegates validation to core logic (pure, testable).
    Saves to the repository after validation passes.
    """
    existing_votes_for_poll = [v for v in _votes if v.poll_id == poll.id]
    validate_vote(poll, voter_id, request.choice, existing_votes_for_poll)

    vote = Vote(
        poll_id=poll.id,
        voter_id=voter_id,
        choice=request.choice,
    )
    _votes.append(vote)
    return vote


def get_results(poll: Poll) -> PollResults:
    poll_votes = [v for v in _votes if v.poll_id == poll.id]
    return tally_votes(poll, poll_votes)

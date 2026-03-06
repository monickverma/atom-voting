"""
Atom Voting — unit tests for core domain logic.

These tests are fast (<1s) and have zero dependencies on HTTP or database.
They document the expected behaviour of every domain rule.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.core.voting import (
    DuplicateVoteError,
    InvalidChoiceError,
    PollClosedError,
    tally_votes,
    validate_vote,
)
from src.models.vote import Poll, Vote


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def make_poll(closed: bool = False) -> Poll:
    closes_at = (
        datetime.now(timezone.utc) - timedelta(days=1)
        if closed
        else datetime.now(timezone.utc) + timedelta(days=1)
    )
    return Poll(
        id="poll_001",
        title="Best language?",
        options=["Python", "Rust", "Go"],
        closes_at=closes_at,
    )


def make_vote(choice: str = "Python", voter_id: str = "voter_001") -> Vote:
    return Vote(poll_id="poll_001", voter_id=voter_id, choice=choice)


# ─── validate_vote ────────────────────────────────────────────────────────────

class TestValidateVote:
    def test_valid_vote_passes(self) -> None:
        poll = make_poll()
        validate_vote(poll, "voter_001", "Python", [])  # should not raise

    def test_raises_on_closed_poll(self) -> None:
        poll = make_poll(closed=True)
        with pytest.raises(PollClosedError) as exc_info:
            validate_vote(poll, "voter_001", "Python", [])
        assert exc_info.value.code == "POLL_CLOSED"

    def test_raises_on_invalid_choice(self) -> None:
        poll = make_poll()
        with pytest.raises(InvalidChoiceError) as exc_info:
            validate_vote(poll, "voter_001", "Java", [])
        assert exc_info.value.code == "INVALID_CHOICE"

    def test_raises_on_duplicate_vote(self) -> None:
        poll = make_poll()
        existing = [make_vote()]
        with pytest.raises(DuplicateVoteError) as exc_info:
            validate_vote(poll, "voter_001", "Rust", existing)
        assert exc_info.value.code == "VOTE_ALREADY_CAST"

    def test_different_voter_can_vote_same_poll(self) -> None:
        poll = make_poll()
        existing = [make_vote(voter_id="voter_001")]
        validate_vote(poll, "voter_002", "Rust", existing)  # should not raise


# ─── tally_votes ──────────────────────────────────────────────────────────────

class TestTallyVotes:
    def test_tally_with_no_votes(self) -> None:
        poll = make_poll()
        results = tally_votes(poll, [])
        assert results.total_votes == 0
        for r in results.results:
            assert r.votes == 0
            assert r.percentage == 0.0

    def test_tally_counts_correctly(self) -> None:
        poll = make_poll()
        votes = [
            make_vote("Python", "v1"),
            make_vote("Python", "v2"),
            make_vote("Rust", "v3"),
        ]
        results = tally_votes(poll, votes)
        assert results.total_votes == 3
        by_option = {r.option: r for r in results.results}
        assert by_option["Python"].votes == 2
        assert by_option["Rust"].votes == 1
        assert by_option["Go"].votes == 0

    def test_tally_percentages_sum_to_100(self) -> None:
        poll = make_poll()
        votes = [make_vote("Python", "v1"), make_vote("Rust", "v2")]
        results = tally_votes(poll, votes)
        total_pct = sum(r.percentage for r in results.results)
        assert abs(total_pct - 100.0) < 0.1

    def test_tally_returns_all_options(self) -> None:
        poll = make_poll()
        results = tally_votes(poll, [])
        assert {r.option for r in results.results} == set(poll.options)


# ─── Poll model ───────────────────────────────────────────────────────────────

class TestPollModel:
    def test_open_poll_is_open(self) -> None:
        poll = make_poll(closed=False)
        assert poll.is_open() is True

    def test_closed_poll_is_not_open(self) -> None:
        poll = make_poll(closed=True)
        assert poll.is_open() is False

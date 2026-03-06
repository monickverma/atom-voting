"""
Atom Voting — API routes (adapter layer).

This file is the HTTP adapter. It knows about HTTP (FastAPI).
It does NOT contain business logic — that lives in services/ and core/.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.core.voting import VotingError
from src.models.vote import CastVoteRequest, Poll, PollResults, Vote
from src.services import vote_service

router = APIRouter(prefix="/api/v1", tags=["voting"])


@router.post("/polls", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_poll(poll: Poll) -> dict:
    """Create a new voting poll."""
    created = vote_service.create_poll(poll)
    return {"data": created.model_dump()}


@router.get("/polls/{poll_id}", response_model=dict)
def get_poll(poll_id: str) -> dict:
    """Retrieve a poll by ID."""
    poll = vote_service.get_poll(poll_id)
    if poll is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "POLL_NOT_FOUND", "message": f"Poll '{poll_id}' not found."},
        )
    return {"data": {**poll.model_dump(), "status": poll.status}}


@router.post("/polls/{poll_id}/vote", response_model=dict)
def cast_vote(poll_id: str, request: CastVoteRequest) -> dict:
    """Cast a vote in a poll. Voter identity is a demo stub — replace with real auth."""
    poll = vote_service.get_poll(poll_id)
    if poll is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "POLL_NOT_FOUND", "message": f"Poll '{poll_id}' not found."},
        )

    # Demo: use a hardcoded voter_id. Replace with JWT claim extraction.
    voter_id = "demo_voter"

    try:
        vote: Vote = vote_service.cast_vote(poll, voter_id, request)
    except VotingError as e:
        status_code = (
            status.HTTP_409_CONFLICT
            if e.code == "VOTE_ALREADY_CAST"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(
            status_code=status_code,
            detail={"code": e.code, "message": e.message},
        ) from e

    return {"data": vote.model_dump()}


@router.get("/polls/{poll_id}/results", response_model=dict)
def get_results(poll_id: str) -> dict:
    """Get aggregated vote results for a poll."""
    poll = vote_service.get_poll(poll_id)
    if poll is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "POLL_NOT_FOUND", "message": f"Poll '{poll_id}' not found."},
        )

    results: PollResults = vote_service.get_results(poll)
    return {"data": results.model_dump()}

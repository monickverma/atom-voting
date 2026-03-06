"""
Atom Voting — API routes (adapter layer).

This file is the HTTP adapter for the cryptographic voting endpoints.
It does NOT contain business logic.
"""
from __future__ import annotations

from typing import Union

from fastapi import APIRouter, HTTPException, status

from src.core.voting import VotingError
from src.models.ballot import ChallengeResponse, SubmitVoteRequest
from src.services import vote_service

router = APIRouter(prefix="/api/v1", tags=["voting"])


@router.post("/ballots", response_model=Union[dict, ChallengeResponse], status_code=status.HTTP_201_CREATED)
async def submit_ballot(request: SubmitVoteRequest) -> Union[dict, ChallengeResponse]:
    """
    Submit an encrypted ballot.
    Action can be CAST (store to ledger) or CHALLENGE (audit & destroy).
    """
    try:
        result = await vote_service.process_ballot(request)
        return {"data": result} if isinstance(result, dict) else result
    except VotingError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": e.code, "message": e.message},
        ) from e


@router.get("/tally", response_model=dict)
def get_tally() -> dict:
    """
    Get the current election tally.
    In a real system, this is only available AFTER the MixNet / threshold ceremony.
    """
    results = vote_service.run_tally()
    return {"data": results}

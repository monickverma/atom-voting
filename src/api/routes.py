"""
Atom Voting — API routes (adapter layer).

This file is the HTTP adapter for the cryptographic voting endpoints.
It does NOT contain business logic.
"""
from __future__ import annotations

from typing import Union

from fastapi import APIRouter, HTTPException, Request, status

from src.core.voting import VotingError
from src.models.ballot import BallotVerification, ChallengeResponse, PrepareVoteRequest, SubmitVoteRequest
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


# ─── Dual-Device Verification Routes ─────────────────────────────────────────

@router.post("/ballots/prepare", status_code=status.HTTP_202_ACCEPTED)
def prepare_ballot(request: PrepareVoteRequest, http_request: Request) -> dict:
    """
    Device A: Submit an encrypted ballot for pending hold.
    Returns the ballot_hash and the verification URL to encode in a QR code.
    The ballot is NOT committed to the ledger yet.
    """
    try:
        base_url = str(http_request.base_url).rstrip("/")
        return vote_service.prepare_ballot(request, base_url=base_url)
    except VotingError as e:
        raise HTTPException(status_code=422, detail={"code": e.code, "message": e.message}) from e


@router.get("/ballots/verify/{ballot_hash}", response_model=BallotVerification)
def get_ballot_for_verification(ballot_hash: str) -> BallotVerification:
    """
    Device B: Retrieve a pending ballot by its hash for voter review before confirmation.
    """
    verification = vote_service.get_pending_ballot(ballot_hash)
    if verification is None:
        raise HTTPException(status_code=404, detail="Pending ballot not found or already confirmed.")
    return verification


@router.post("/ballots/confirm/{ballot_hash}", status_code=status.HTTP_201_CREATED)
async def confirm_ballot(ballot_hash: str) -> dict:
    """
    Device B: Confirm a pending ballot. This is the point of no return.
    The ballot is moved from the pending store to the immutable public ledger.
    A WebSocket broadcast fires to all connected clients.
    """
    try:
        return await vote_service.confirm_ballot(ballot_hash)
    except VotingError as e:
        raise HTTPException(status_code=422, detail={"code": e.code, "message": e.message}) from e


# ─── Public Blockchain Ledger API ───────────────────────────────────────────────────

@router.get("/ledger", response_model=dict)
def list_ledger_blocks(
    skip: int = 0,
    limit: int = 50,
) -> dict:
    """
    Public read-only view of the entire blockchain ledger.
    Returns encrypted ballot metadata only — no identity, no decrypted votes.
    Ordered newest-first. Supports pagination via skip/limit query params.
    """
    return vote_service.get_ledger_blocks(skip=skip, limit=limit)


@router.get("/ledger/{vote_id}", response_model=dict)
def get_ledger_block(vote_id: str) -> dict:
    """
    Look up a single ledger block by its vote_id for voter receipt self-verification.
    Returns 404 if the vote_id is not found on the ledger.
    """
    block = vote_service.get_ledger_block(vote_id)
    if block is None:
        raise HTTPException(
            status_code=404,
            detail="Vote ID not found on the public ledger."
        )
    return block

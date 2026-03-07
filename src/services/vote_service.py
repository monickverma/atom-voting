"""
Atom Voting — vote service.

Orchestrates cryptographic use cases using core domain logic.
This layer owns the "what to do" — it calls core for domain decisions
and manages the append-only ledger state.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.api.websockets import EventType, manager

from src.core.crypto import DEMO_PRVK, DEMO_PUBK, decode_candidate, decrypt
from src.core.voting import (
    compute_receipt_hash,
    compute_vote_id,
    tally_votes,
    validate_ballot,
)
from src.models.ballot import (
    BallotVerification,
    ChallengeResponse,
    PendingBallot,
    PrepareVoteRequest,
    SubmitVoteRequest,
    VoteAction,
    VoteBlock,
)

# In-memory stores for hackathon demo. Replace with real PG adapter.
_ledger: list[VoteBlock] = []
_seen_nonces: set[str] = set()
_pending_ballots: dict[str, PendingBallot] = {}  # ballot_hash -> PendingBallot

# Real cryptographic keys! (Demo defaults)
ELECTION_PUBLIC_KEY = DEMO_PUBK
IS_ELECTION_OPEN = True

# Code mapping for tallying (would be managed by Code Server)
CODE_MAP = {4427: "Candidate B", 8391: "Candidate A", 9102: "Candidate C"}
VALID_CODES = list(CODE_MAP.keys())

# Real cryptographic tally — tracking what we've decrypted so far.
# In production, decryption happens via threshold shares.
_fake_credentials: set[str] = set()


async def process_ballot(request: SubmitVoteRequest) -> dict[str, str] | ChallengeResponse:
    """
    Process an incoming ballot submission.
    Handles both CAST and CHALLENGE actions.
    """
    # 1. Pure domain validation (throws VotingError if invalid)
    validate_ballot(request, ELECTION_PUBLIC_KEY, VALID_CODES, _seen_nonces, IS_ELECTION_OPEN)

    if request.action == VoteAction.CHALLENGE:
        # Challenge audit: Server decrypts the ElGamal ciphertext, reveals candidate, and DESTROYS ballot
        c1 = int(request.encrypted_ballot.c1, 16)
        c2 = int(request.encrypted_ballot.c2, 16)
        
        # In a real system, the server decrypts using threshold shares. For the demo, we use DEMO_PRVK.
        gm = decrypt(c1, c2, DEMO_PRVK)
        code = decode_candidate(gm, VALID_CODES) or 0
        candidate_name = CODE_MAP.get(code, "Unknown")
        
        _seen_nonces.add(request.encrypted_ballot.nonce_id)
        return ChallengeResponse(
            decrypted_code=code,
            candidate_mapping_hint=f"{code} → {candidate_name}",
        )

    # 2. Cast action: save to immutable ledger
    vote_id = compute_vote_id(request.encrypted_ballot)
    timestamp = datetime.now(timezone.utc)
    receipt_hash = compute_receipt_hash(vote_id, request.credential_hash, timestamp)

    block = VoteBlock(
        vote_id=vote_id,
        ciphertext=request.encrypted_ballot,
        credential_hash=request.credential_hash,
        timestamp=timestamp,
        revote_pointer=request.revote_pointer,
        zk_proof=request.zk_proof,
        receipt_hash=receipt_hash,
    )

    _ledger.append(block)
    _seen_nonces.add(request.encrypted_ballot.nonce_id)

    # Broadcast real-time update to hackathon observers
    await manager.broadcast(
        EventType.VOTE_CAST,
        {
            "vote_id": vote_id,
            "timestamp": timestamp.isoformat(),
            "receipt_hash": receipt_hash,
        },
    )

    return {"receipt_hash": receipt_hash, "vote_id": vote_id}


def run_tally() -> dict[str, int]:
    """
    Run the real election tally according to JCJ and revote rules.
    Decrypts the ciphertexts using DEMO_PRVK. 
    (In production, MixNet shuffles ledger before threshold decryption).
    """
    decrypted_codes: dict[str, int] = {}
    
    for block in _ledger:
        c1 = int(block.ciphertext.c1, 16)
        c2 = int(block.ciphertext.c2, 16)
        gm = decrypt(c1, c2, DEMO_PRVK)
        code = decode_candidate(gm, VALID_CODES)
        if code is not None:
            decrypted_codes[block.vote_id] = code
            
    return tally_votes(_ledger, _fake_credentials, CODE_MAP, decrypted_codes)


# ─── Dual-Device Two-Phase Commit ───────────────────────────────────────────

from src.core.voting import compute_vote_id as _compute_vote_id  # noqa: E402


def prepare_ballot(request: PrepareVoteRequest, base_url: str = "http://localhost:8000") -> dict[str, str]:
    """
    Phase 1 (Device A): Validate, encrypt, and store ballot as PENDING.
    Returns a ballot_hash that is encoded in the QR code.
    The ballot is NOT added to the ledger yet.
    """
    # Compute a deterministic hash from the ciphertext to use as a QR payload key
    import hashlib
    ballot_hash = hashlib.sha256(
        f"{request.encrypted_ballot.c1}:{request.encrypted_ballot.c2}:{request.encrypted_ballot.nonce_id}".encode()
    ).hexdigest()[:16]

    pending = PendingBallot(
        ballot_hash=ballot_hash,
        encrypted_ballot=request.encrypted_ballot,
        zk_proof=request.zk_proof,
        credential_hash=request.credential_hash,
        revote_pointer=request.revote_pointer,
    )
    _pending_ballots[ballot_hash] = pending

    # Use the actual server base_url so QR works from any device on the network
    verification_url = f"{base_url}/?verify={ballot_hash}"
    return {"ballot_hash": ballot_hash, "verification_url": verification_url}


def get_pending_ballot(ballot_hash: str) -> BallotVerification | None:
    """
    Phase 2 (Device B retrieval): Returns the pending ballot details for the voter to review.
    """
    pending = _pending_ballots.get(ballot_hash)
    if pending is None:
        return None

    return BallotVerification(
        ballot_hash=pending.ballot_hash,
        encrypted_c1_preview=pending.encrypted_ballot.c1[:32],
        encrypted_c2_preview=pending.encrypted_ballot.c2[:32],
        confirmed=pending.confirmed,
    )


async def confirm_ballot(ballot_hash: str) -> dict[str, str]:
    """
    Phase 2 (Device B confirms): Moves ballot from PENDING to the immutable ledger.
    Fires the WebSocket broadcast. This is the point of no return.
    """
    pending = _pending_ballots.get(ballot_hash)
    if pending is None:
        from src.core.voting import VotingError
        raise VotingError("BALLOT_NOT_FOUND", "No pending ballot with this hash. It may have expired.")

    if pending.confirmed:
        from src.core.voting import VotingError
        raise VotingError("ALREADY_CONFIRMED", "This ballot has already been confirmed.")

    # Two-phase commit: move from pending to ledger
    vote_id = _compute_vote_id(pending.encrypted_ballot)
    timestamp = datetime.now(timezone.utc)
    receipt_hash = compute_receipt_hash(vote_id, pending.credential_hash, timestamp)

    block = VoteBlock(
        vote_id=vote_id,
        ciphertext=pending.encrypted_ballot,
        credential_hash=pending.credential_hash,
        timestamp=timestamp,
        revote_pointer=pending.revote_pointer,
        zk_proof=pending.zk_proof,
        receipt_hash=receipt_hash,
    )

    _ledger.append(block)
    _seen_nonces.add(pending.encrypted_ballot.nonce_id)

    # Mark as confirmed in the pending store
    _pending_ballots[ballot_hash] = pending.model_copy(update={"confirmed": True})

    # Broadcast to all WebSocket listeners
    await manager.broadcast(
        EventType.VOTE_CAST,
        {
            "vote_id": vote_id,
            "timestamp": timestamp.isoformat(),
            "receipt_hash": receipt_hash,
        },
    )

    return {"receipt_hash": receipt_hash, "vote_id": vote_id, "ballot_hash": ballot_hash}

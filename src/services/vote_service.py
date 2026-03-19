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

# Fast O(1) index: credential_hash -> latest vote_id on the ledger
# Updated atomically whenever a ballot is confirmed.
_latest_vote_per_credential: dict[str, str] = {}

# JCJ Fake Credentials registry.
# Maps voter_id -> {"real": real_credential_hash, "fake": fake_credential_hash}.
# The `_fake_credentials` set is the authoritative filter used by tally_votes().
_voter_credentials: dict[str, dict[str, str]] = {}
_fake_credentials: set[str] = set()
# Real cryptographic keys! (Demo defaults)
ELECTION_PUBLIC_KEY = DEMO_PUBK
IS_ELECTION_OPEN = True

# Code mapping for tallying (would be managed by Code Server)
CODE_MAP = {4427: "Candidate B", 8391: "Candidate A", 9102: "Candidate C"}
VALID_CODES = list(CODE_MAP.keys())


# ─── JCJ Credential Management ──────────────────────────────────────────────

def issue_credentials(voter_id: str) -> dict[str, str]:
    """
    Generate and register a pair of credentials for a voter (JCJ scheme).
    - real_hash: the credential that will be counted in the final tally.
    - fake_hash: looks identical on the ledger; silently discarded at tally time.

    Both hashes are cryptographically indistinguishable on the public ledger.
    A coercer who forces the voter to reveal their credential gets the fake one.
    """
    import hashlib, secrets
    if voter_id in _voter_credentials:
        return _voter_credentials[voter_id]

    salt = secrets.token_hex(16)
    real_hash = hashlib.sha256(f"real:{voter_id}:{salt}".encode()).hexdigest()[:32]
    fake_hash = hashlib.sha256(f"fake:{voter_id}:{salt}".encode()).hexdigest()[:32]

    _voter_credentials[voter_id] = {"real": real_hash, "fake": fake_hash}
    # Register the fake hash so tally_votes() silently discards it
    _fake_credentials.add(fake_hash)

    return {"real": real_hash, "fake": fake_hash}


def get_voter_credentials(voter_id: str) -> dict[str, str] | None:
    """Retrieve existing credentials for a voter. Returns None if not registered."""
    return _voter_credentials.get(voter_id)


# ─── Public Blockchain Ledger Read API ────────────────────────────────────────

def get_ledger_blocks(skip: int = 0, limit: int = 50) -> dict:
    """
    Return a paginated, publicly auditable view of the blockchain.
    Blocks are returned newest-first (reverse chronological).
    Sensitive fields (identity, decrypted votes) are NEVER included.
    """
    total = len(_ledger)
    # newest first
    page = list(reversed(_ledger))[skip : skip + limit]
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "blocks": [
            {
                "vote_id": b.vote_id,
                "credential_hash": b.credential_hash,
                "timestamp": b.timestamp.isoformat(),
                "receipt_hash": b.receipt_hash,
                "revote_pointer": b.revote_pointer,
                # Redacted: ciphertext and zk_proof kept off public API for demo
                # In production these ARE public for auditability.
                "has_zk_proof": b.zk_proof is not None,
            }
            for b in page
        ],
    }


def get_ledger_block(vote_id: str) -> dict | None:
    """
    Look up a single block by vote_id (used for voter receipt verification).
    Returns None if not found.
    """
    block = next((b for b in _ledger if b.vote_id == vote_id), None)
    if block is None:
        return None
    return {
        "vote_id": block.vote_id,
        "credential_hash": block.credential_hash,
        "timestamp": block.timestamp.isoformat(),
        "receipt_hash": block.receipt_hash,
        "revote_pointer": block.revote_pointer,
        "has_zk_proof": block.zk_proof is not None,
        "is_latest_for_credential": _latest_vote_per_credential.get(block.credential_hash) == block.vote_id,
    }


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

    # Count how many times this credential has already voted on the ledger
    prior_count = len([b for b in _ledger if b.credential_hash == pending.credential_hash])
    is_revote = pending.credential_hash in _latest_vote_per_credential

    return BallotVerification(
        ballot_hash=pending.ballot_hash,
        encrypted_c1_preview=pending.encrypted_ballot.c1[:32],
        encrypted_c2_preview=pending.encrypted_ballot.c2[:32],
        confirmed=pending.confirmed,
        is_revote=str(is_revote).lower(),
        revote_count=str(prior_count + 1),  # +1 for the current pending vote
    )


async def confirm_ballot(ballot_hash: str) -> dict[str, str]:
    """
    Phase 2 (Device B confirms): Moves ballot from PENDING to the immutable ledger.
    Automatically detects if this credential has voted before and sets revote_pointer.
    Fires the WebSocket broadcast. This is the point of no return.
    """
    pending = _pending_ballots.get(ballot_hash)
    if pending is None:
        from src.core.voting import VotingError
        raise VotingError("BALLOT_NOT_FOUND", "No pending ballot with this hash. It may have expired.")

    if pending.confirmed:
        from src.core.voting import VotingError
        raise VotingError("ALREADY_CONFIRMED", "This ballot has already been confirmed.")

    # AUTO-DETECT REVOTE: if this credential has already cast a ballot,
    # chain the new vote to the previous one via revote_pointer.
    # This happens server-side so the UI just needs to send the credential_hash.
    prior_vote_id = _latest_vote_per_credential.get(pending.credential_hash)
    resolved_revote_pointer = prior_vote_id  # None on first vote, vote_id on revote
    is_revote = prior_vote_id is not None

    # Two-phase commit: move from pending to ledger
    vote_id = _compute_vote_id(pending.encrypted_ballot)
    timestamp = datetime.now(timezone.utc)
    receipt_hash = compute_receipt_hash(vote_id, pending.credential_hash, timestamp)

    block = VoteBlock(
        vote_id=vote_id,
        ciphertext=pending.encrypted_ballot,
        credential_hash=pending.credential_hash,
        timestamp=timestamp,
        revote_pointer=resolved_revote_pointer,  # auto-injected
        zk_proof=pending.zk_proof,
        receipt_hash=receipt_hash,
    )

    _ledger.append(block)
    _seen_nonces.add(pending.encrypted_ballot.nonce_id)

    # Update the O(1) index so the NEXT vote from this credential points here
    _latest_vote_per_credential[pending.credential_hash] = vote_id

    # Mark as confirmed in the pending store
    _pending_ballots[ballot_hash] = pending.model_copy(update={"confirmed": True})

    # Count how many times this credential has voted (for the receipt display)
    revote_count = len([b for b in _ledger if b.credential_hash == pending.credential_hash])

    # Broadcast to all WebSocket listeners
    await manager.broadcast(
        EventType.VOTE_CAST,
        {
            "vote_id": vote_id,
            "timestamp": timestamp.isoformat(),
            "receipt_hash": receipt_hash,
            "is_revote": is_revote,
            "revote_count": revote_count,
        },
    )

    return {
        "receipt_hash": receipt_hash,
        "vote_id": vote_id,
        "ballot_hash": ballot_hash,
        "is_revote": str(is_revote).lower(),
        "revote_count": str(revote_count),
        "revote_pointer": resolved_revote_pointer or "",
    }

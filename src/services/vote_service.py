"""
Atom Voting — vote service.

Orchestrates cryptographic use cases using core domain logic.
This layer owns the "what to do" — it calls core for domain decisions
and manages the append-only ledger state.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.core.voting import (
    compute_receipt_hash,
    compute_vote_id,
    tally_votes,
    validate_ballot,
)
from src.models.ballot import (
    ChallengeResponse,
    SubmitVoteRequest,
    VoteAction,
    VoteBlock,
)

# In-memory stores for hackathon demo. Replace with real PG adapter.
_ledger: list[VoteBlock] = []
_seen_nonces: set[str] = set()

# Stub election public key (would come from DB/Config)
ELECTION_PUBLIC_KEY = "stub-election-public-key"
IS_ELECTION_OPEN = True

# Code mapping for tallying (would be managed by Code Server)
CODE_MAP = {4427: "Candidate B", 8391: "Candidate A", 9102: "Candidate C"}
# For the hackathon demo, we pretend we know how to decrypt the stub ciphertexts
_decrypted_codes: dict[str, int] = {}
_fake_credentials: set[str] = set()


def process_ballot(request: SubmitVoteRequest) -> dict[str, str] | ChallengeResponse:
    """
    Process an incoming ballot submission.
    Handles both CAST and CHALLENGE actions.
    """
    # 1. Pure domain validation (throws VotingError if invalid)
    validate_ballot(request, ELECTION_PUBLIC_KEY, _seen_nonces, IS_ELECTION_OPEN)

    if request.action == VoteAction.CHALLENGE:
        # Challenge audit: reveal what the code was, do NOT store the ballot
        # In a real system, the server decrypts the ElGamal ciphertext using threshold shares here.
        # For the stub, we just pretend it was 4427.
        _seen_nonces.add(request.encrypted_ballot.nonce_id)
        return ChallengeResponse(
            decrypted_code=4427,
            candidate_mapping_hint="4427 → Candidate B",
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

    # Cheat for the demo tally: we store the stub code
    # Real tally uses threshold decryption AFTER mixnet.
    _decrypted_codes[vote_id] = 4427

    return {"receipt_hash": receipt_hash, "vote_id": vote_id}


def run_tally() -> dict[str, int]:
    """Run the election tally according to JCJ and revote rules."""
    return tally_votes(_ledger, _fake_credentials, CODE_MAP, _decrypted_codes)

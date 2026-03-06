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
    ChallengeResponse,
    SubmitVoteRequest,
    VoteAction,
    VoteBlock,
)

# In-memory stores for hackathon demo. Replace with real PG adapter.
_ledger: list[VoteBlock] = []
_seen_nonces: set[str] = set()

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

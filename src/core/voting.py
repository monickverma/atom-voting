"""
Atom Voting — core domain logic for the cryptographic voting protocol.

Pure functions with no framework or I/O imports.
All domain rules are expressed here and tested in isolation.

Protocol reference: docs/architecture.md
Encryption ADR: docs/decisions/002-encryption-scheme.md
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from src.models.ballot import (
    CredentialType,
    EncryptedBallot,
    SubmitVoteRequest,
    VoteBlock,
    ZKProof,
)


# ─── Domain Errors ────────────────────────────────────────────────────────────

class VotingError(Exception):
    """Base class for all voting domain errors."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ElectionClosedError(VotingError):
    def __init__(self) -> None:
        super().__init__("ELECTION_CLOSED", "The voting window has closed. No new votes accepted.")


class InvalidZKProofError(VotingError):
    def __init__(self) -> None:
        super().__init__("INVALID_ZK_PROOF", "Zero-knowledge proof verification failed.")


class DuplicateNonceError(VotingError):
    def __init__(self) -> None:
        super().__init__("DUPLICATE_NONCE", "This ballot nonce has already been submitted.")


# ─── Vote Ledger Operations ────────────────────────────────────────────────────

def compute_vote_id(encrypted_ballot: EncryptedBallot) -> str:
    """
    Deterministic vote ID = hash(c1 || c2 || nonce_id).
    Stored as VoteID on the public ledger.
    Pure function — same input always produces same output.
    """
    raw = f"{encrypted_ballot.c1}:{encrypted_ballot.c2}:{encrypted_ballot.nonce_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def compute_receipt_hash(vote_id: str, credential_hash: str, timestamp: datetime) -> str:
    """
    Voter-verifiable receipt = hash(vote_id || credential_hash || timestamp).
    Voter stores this and can later verify presence on public ledger.
    """
    raw = f"{vote_id}:{credential_hash}:{timestamp.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16].upper()


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_ballot(
    request: SubmitVoteRequest,
    election_public_key: int,
    valid_codes: list[int],
    seen_nonces: set[str],
    election_open: bool,
) -> None:
    """
    Validate a ballot submission against all domain rules.
    Raises VotingError subclass on any failure.

    This is pure domain logic — no database, no HTTP.
    Tests can call this directly without any running infrastructure.
    """
    if not election_open:
        raise ElectionClosedError()

    # Replay attack prevention — each nonce must be unique
    if request.encrypted_ballot.nonce_id in seen_nonces:
        raise DuplicateNonceError()

    # ZK proof verification — proves ballot encrypts a valid candidate
    if not request.zk_proof.verify(request.encrypted_ballot, election_public_key, valid_codes):
        raise InvalidZKProofError()


# ─── RevotePointer Chain ──────────────────────────────────────────────────────

def resolve_latest_vote(
    credential_hash: str,
    ledger: list[VoteBlock],
) -> VoteBlock | None:
    """
    Return the latest valid VoteBlock for a given credential.
    Earlier votes in a revote chain are preserved but ignored in tally.

    Rule: latest VoteBlock with matching credential_hash, no newer RevotePointer
    pointing to it = the counted vote.
    """
    # Collect all blocks for this credential
    credential_blocks = [b for b in ledger if b.credential_hash == credential_hash]
    if not credential_blocks:
        return None

    # The voted-upon block is referenced by a later revote_pointer — so the
    # one that is NOT referenced by any other block is the latest.
    referenced_ids = {b.revote_pointer for b in credential_blocks if b.revote_pointer}
    unreferenced = [b for b in credential_blocks if b.vote_id not in referenced_ids]

    if not unreferenced:
        return None  # Defensive: should not happen in a well-formed ledger

    # Sort by timestamp as tiebreaker (should only be one)
    return sorted(unreferenced, key=lambda b: b.timestamp)[-1]


# ─── Tally ────────────────────────────────────────────────────────────────────

def tally_votes(
    ledger: list[VoteBlock],
    fake_credential_hashes: set[str],
    code_to_candidate: dict[int, str],
    decrypted_codes: dict[str, int],  # vote_id → decrypted candidate code
) -> dict[str, int]:
    """
    Compute the final election tally.

    Called AFTER:
      1. Ledger is frozen
      2. MixNet has shuffled and re-encrypted all ciphertexts
      3. Trustees have performed threshold decryption

    Parameters:
      ledger:                  All VoteBlocks from the ledger
      fake_credential_hashes:  Set of hashes corresponding to fake credentials (JCJ filter)
      code_to_candidate:       Mapping from numeric code → candidate name
      decrypted_codes:         Post-decryption mapping from vote_id → numeric code

    Returns: dict of candidate_name → vote_count
    """
    # Initialise counts for all known candidates
    tally: dict[str, int] = {name: 0 for name in code_to_candidate.values()}

    # Group ledger by credential — take only the latest vote per credential
    seen_credentials: set[str] = set()
    for block in sorted(ledger, key=lambda b: b.timestamp):
        cred_hash = block.credential_hash

        if cred_hash in seen_credentials:
            continue  # Earlier vote — revoted away

        if cred_hash in fake_credential_hashes:
            continue  # JCJ: discard fake credential votes

        latest = resolve_latest_vote(cred_hash, ledger)
        if latest is None or latest.vote_id not in decrypted_codes:
            continue

        code = decrypted_codes[latest.vote_id]
        candidate = code_to_candidate.get(code)
        if candidate and candidate in tally:
            tally[candidate] += 1

        seen_credentials.add(cred_hash)

    return tally

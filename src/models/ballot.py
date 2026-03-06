"""
Atom Voting — cryptographic ballot models.

These are the real domain models for the cryptographic voting system.
v1.0 uses stub encryption interfaces — real ElGamal is planned for v1.1.
See docs/decisions/002-encryption-scheme.md for the encryption ADR.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────────────────


class CredentialType(str, Enum):
    REAL = "real"
    FAKE = "fake"


class VoteAction(str, Enum):
    CAST = "cast"
    CHALLENGE = "challenge"


class ElectionPhase(str, Enum):
    SETUP = "setup"       # Pre-election: key ceremony, code sheet distribution
    VOTING = "voting"     # Voting window open
    CLOSED = "closed"     # Voting window closed, awaiting mix + tally
    TALLIED = "tallied"   # Final results published


# ─── Credential Model ──────────────────────────────────────────────────────────


class Credential(BaseModel):
    """
    A voter credential. Each voter receives two:
      - RealCredential: counted in final tally
      - FakeCredential: stored on ledger, discarded at tally time

    Based on the JCJ (Juels-Catalano-Jakobsson) coercion-resistant scheme.
    On the public ledger, both types are cryptographically indistinguishable.
    """

    credential_id: str
    credential_type: CredentialType
    voter_id: str

    def credential_hash(self) -> str:
        """
        Return the public hash stored on ledger.
        The raw credential_id is NEVER stored publicly.
        """
        import hashlib
        return hashlib.sha256(self.credential_id.encode()).hexdigest()


# ─── Ballot Models ────────────────────────────────────────────────────────────


class CandidateCode(BaseModel):
    """
    A per-voter, per-candidate numeric code from the code sheet.
    Voter enters this number — not the candidate's name.
    Malware observing keystrokes sees only a number with no candidate context.
    """

    code: int = Field(..., description="Numeric code from voter's code sheet")


class EncryptedBallot(BaseModel):
    """
    An ElGamal-encrypted ballot ciphertext.
    v1.0: ciphertext fields are stubs (plain ints for testing).
    v1.1: replace with real ElGamal group elements.

    See docs/decisions/002-encryption-scheme.md.
    """

    c1: str = Field(..., description="g^r mod p (ElGamal first component)")
    c2: str = Field(..., description="g^m · h^r mod p (ElGamal second component)")
    nonce_id: str = Field(..., description="Unique nonce ID — ensures fresh encryption per vote")

    @classmethod
    def stub_encrypt(cls, code: int, election_public_key: str) -> "EncryptedBallot":
        """
        STUB ONLY — returns deterministic fake ciphertext for testing.
        Replace with real ElGamal in v1.1 (#5).
        """
        import hashlib
        nonce_id = hashlib.sha256(f"{code}:{election_public_key}:{id(cls)}".encode()).hexdigest()[:16]
        # Stub: encode as hex so the structure is correct shape
        c1 = hashlib.sha256(f"c1:{nonce_id}:{code}".encode()).hexdigest()
        c2 = hashlib.sha256(f"c2:{nonce_id}:{election_public_key}:{code}".encode()).hexdigest()
        return cls(c1=c1, c2=c2, nonce_id=nonce_id)


class ZKProof(BaseModel):
    """
    Zero-knowledge proof that the encrypted ballot contains a valid candidate code.
    v1.0: stub (always returns valid). Real Chaum-Pedersen proof in v1.1 (#7).
    """

    proof_data: str = Field(..., description="Serialised ZK proof bytes (hex)")
    is_stub: bool = Field(default=True, description="True if this is a stub proof — not production-valid")

    @classmethod
    def stub_proof(cls, encrypted_ballot: EncryptedBallot) -> "ZKProof":
        """STUB: generate a placeholder proof. Replace in v1.1 (#7)."""
        return cls(proof_data=f"stub:{encrypted_ballot.nonce_id}", is_stub=True)

    def verify(self, encrypted_ballot: EncryptedBallot, election_public_key: str) -> bool:
        """STUB: always returns True. Real Chaum-Pedersen verification in v1.1 (#7)."""
        if self.is_stub:
            return True
        # TODO: implement real ZK verification
        raise NotImplementedError("Real ZK proof verification not yet implemented — see issue #7")


# ─── Vote Block (Ledger Entry) ────────────────────────────────────────────────


class VoteBlock(BaseModel):
    """
    A single entry in the immutable vote ledger.
    Maps directly to the blockchain data model in the system design.
    Only the latest VoteBlock per credential is counted in the final tally.
    """

    vote_id: str                          # hash(EncryptedBallot)
    ciphertext: EncryptedBallot
    credential_hash: str                  # hash(credential_id) — not the raw credential
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revote_pointer: Optional[str] = None  # VoteID of the previous vote (null if first)
    zk_proof: ZKProof
    receipt_hash: str                     # Voter's verifiable receipt

    @property
    def is_revote(self) -> bool:
        return self.revote_pointer is not None


# ─── Cast / Challenge Request ─────────────────────────────────────────────────


class SubmitVoteRequest(BaseModel):
    """API request to submit an encrypted ballot."""

    encrypted_ballot: EncryptedBallot
    zk_proof: ZKProof
    credential_hash: str
    action: VoteAction = VoteAction.CAST
    revote_pointer: Optional[str] = None


class ChallengeResponse(BaseModel):
    """
    Response to a CHALLENGE action.
    Server decrypts temporarily and reveals the candidate code.
    The ballot is then DESTROYED — not stored, not counted.
    """

    decrypted_code: int
    candidate_mapping_hint: str  # e.g. "4427 → Candidate B"
    ballot_destroyed: bool = True

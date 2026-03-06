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
    c1 and c2 are hex-encoded strings representing the exponential ElGamal ciphertext.
    """

    c1: str = Field(..., description="g^r mod p (hex string)")
    c2: str = Field(..., description="g^m · h^r mod p (hex string)")
    nonce_id: str = Field(..., description="Unique nonce ID — ensures fresh encryption per vote")

    @classmethod
    def encrypt_vote(cls, code: int, election_public_key: int) -> tuple["EncryptedBallot", int]:
        """Real exponential ElGamal encryption."""
        from src.core.crypto import encrypt
        import secrets
        
        c1, c2, r = encrypt(code, election_public_key)
        nonce_id = secrets.token_hex(16)
        
        ballot = cls(c1=hex(c1)[2:], c2=hex(c2)[2:], nonce_id=nonce_id)
        return ballot, r

    @classmethod
    def stub_encrypt(cls, code: int, election_public_key: str | int) -> "EncryptedBallot":
        """STUB ONLY — for backward-compatible pure domain tests."""
        import hashlib
        nonce_id = hashlib.sha256(f"{code}:{election_public_key}:{id(cls)}".encode()).hexdigest()[:16]
        c1 = hashlib.sha256(f"c1:{nonce_id}:{code}".encode()).hexdigest()
        c2 = hashlib.sha256(f"c2:{nonce_id}:{election_public_key}:{code}".encode()).hexdigest()
        return cls(c1=c1, c2=c2, nonce_id=nonce_id)


class ZKProof(BaseModel):
    """
    Zero-knowledge proof that the encrypted ballot contains a valid candidate code.
    Uses Cramer-Damgård-Schoenmakers Disjunctive ZK Proof.
    """

    proof_data: dict[str, list[str]] = Field(..., description="Serialised ZK proof (hex strings)")
    is_stub: bool = Field(default=False, description="True if this is a stub proof")

    @classmethod
    def generate(
        cls, code: int, r: int, ballot: EncryptedBallot, election_public_key: int, valid_codes: list[int]
    ) -> "ZKProof":
        """Generate a real Cramer-Damgård-Schoenmakers Disjunctive ZK Proof."""
        from src.core.crypto import generate_disjunctive_zkp
        
        c1 = int(ballot.c1, 16)
        c2 = int(ballot.c2, 16)
        
        proof_ints = generate_disjunctive_zkp(code, r, c1, c2, election_public_key, valid_codes)
        
        proof_hex = {
            "challenges": [hex(c)[2:] for c in proof_ints["challenges"]],
            "responses": [hex(resp)[2:] for resp in proof_ints["responses"]],
        }
        
        return cls(proof_data=proof_hex, is_stub=False)

    def verify(self, encrypted_ballot: EncryptedBallot, election_public_key: int, valid_codes: list[int]) -> bool:
        """Verify the Cramer-Damgård-Schoenmakers Disjunctive ZK Proof."""
        if self.is_stub:
            return True
            
        from src.core.crypto import verify_disjunctive_zkp
        
        c1 = int(encrypted_ballot.c1, 16)
        c2 = int(encrypted_ballot.c2, 16)
        
        challenges = self.proof_data.get("challenges", [])
        responses = self.proof_data.get("responses", [])
        
        proof_ints = {
            "challenges": [int(c, 16) for c in challenges],
            "responses": [int(resp, 16) for resp in responses],
        }
        
        return verify_disjunctive_zkp(c1, c2, election_public_key, valid_codes, proof_ints)

    @classmethod
    def stub_proof(cls, encrypted_ballot: EncryptedBallot) -> "ZKProof":
        """STUB: placeholder for backward-compatible tests."""
        return cls(proof_data={"stub": []}, is_stub=True)


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

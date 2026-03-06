"""
Atom Voting — unit tests for the cryptographic voting protocol core logic.

All tests are fast (<1s), have zero dependencies on HTTP or database.
They document every domain rule for contributors.
"""
from __future__ import annotations

import pytest

from src.core.voting import (
    DuplicateNonceError,
    ElectionClosedError,
    InvalidZKProofError,
    compute_receipt_hash,
    compute_vote_id,
    resolve_latest_vote,
    tally_votes,
    validate_ballot,
)
from src.models.ballot import (
    CredentialType,
    EncryptedBallot,
    SubmitVoteRequest,
    VoteAction,
    VoteBlock,
    ZKProof,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

ELECTION_PK = "stub-election-public-key"


def make_ballot(code: int = 4427, nonce: str = "nonce001") -> EncryptedBallot:
    ballot = EncryptedBallot.stub_encrypt(code, ELECTION_PK)
    # Override nonce for deterministic testing
    return ballot.model_copy(update={"nonce_id": nonce})


def make_zk_proof(ballot: EncryptedBallot) -> ZKProof:
    return ZKProof.stub_proof(ballot)


def make_request(
    ballot: EncryptedBallot | None = None,
    action: VoteAction = VoteAction.CAST,
    credential_hash: str = "cred_hash_001",
    revote_pointer: str | None = None,
) -> SubmitVoteRequest:
    b = ballot or make_ballot()
    return SubmitVoteRequest(
        encrypted_ballot=b,
        zk_proof=make_zk_proof(b),
        credential_hash=credential_hash,
        action=action,
        revote_pointer=revote_pointer,
    )


def make_vote_block(
    credential_hash: str = "cred001",
    vote_id: str | None = None,
    revote_pointer: str | None = None,
) -> VoteBlock:
    ballot = make_ballot()
    vid = vote_id or compute_vote_id(ballot)
    receipt = compute_receipt_hash(vid, credential_hash, __import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    return VoteBlock(
        vote_id=vid,
        ciphertext=ballot,
        credential_hash=credential_hash,
        zk_proof=make_zk_proof(ballot),
        receipt_hash=receipt,
        revote_pointer=revote_pointer,
    )


# ─── validate_ballot ──────────────────────────────────────────────────────────

class TestValidateBallot:
    def test_valid_ballot_passes(self) -> None:
        req = make_request()
        validate_ballot(req, ELECTION_PK, set(), election_open=True)  # should not raise

    def test_raises_when_election_closed(self) -> None:
        req = make_request()
        with pytest.raises(ElectionClosedError) as exc:
            validate_ballot(req, ELECTION_PK, set(), election_open=False)
        assert exc.value.code == "ELECTION_CLOSED"

    def test_raises_on_duplicate_nonce(self) -> None:
        ballot = make_ballot(nonce="nonce_dup")
        req = make_request(ballot=ballot)
        seen = {ballot.nonce_id}
        with pytest.raises(DuplicateNonceError) as exc:
            validate_ballot(req, ELECTION_PK, seen, election_open=True)
        assert exc.value.code == "DUPLICATE_NONCE"

    def test_unique_nonce_always_passes(self) -> None:
        req1 = make_request(ballot=make_ballot(nonce="n001"))
        req2 = make_request(ballot=make_ballot(nonce="n002"))
        seen: set[str] = set()
        validate_ballot(req1, ELECTION_PK, seen, election_open=True)
        seen.add(req1.encrypted_ballot.nonce_id)
        validate_ballot(req2, ELECTION_PK, seen, election_open=True)  # should pass

    def test_stub_zk_proof_is_valid(self) -> None:
        ballot = make_ballot()
        proof = ZKProof.stub_proof(ballot)
        assert proof.verify(ballot, ELECTION_PK) is True


# ─── compute_vote_id ──────────────────────────────────────────────────────────

class TestComputeVoteId:
    def test_deterministic(self) -> None:
        ballot = make_ballot(nonce="fixed_nonce")
        assert compute_vote_id(ballot) == compute_vote_id(ballot)

    def test_different_nonces_produce_different_ids(self) -> None:
        b1 = make_ballot(nonce="n_a")
        b2 = make_ballot(nonce="n_b")
        assert compute_vote_id(b1) != compute_vote_id(b2)


# ─── resolve_latest_vote ─────────────────────────────────────────────────────

class TestResolveLatestVote:
    def test_single_vote_is_latest(self) -> None:
        block = make_vote_block(credential_hash="cred1", vote_id="vote_a")
        result = resolve_latest_vote("cred1", [block])
        assert result is not None
        assert result.vote_id == "vote_a"

    def test_revote_makes_earlier_vote_ignored(self) -> None:
        vote1 = make_vote_block(credential_hash="cred1", vote_id="vote_a")
        vote2 = make_vote_block(credential_hash="cred1", vote_id="vote_b", revote_pointer="vote_a")
        result = resolve_latest_vote("cred1", [vote1, vote2])
        assert result is not None
        assert result.vote_id == "vote_b"

    def test_returns_none_for_unknown_credential(self) -> None:
        block = make_vote_block(credential_hash="cred1")
        assert resolve_latest_vote("unknown_cred", [block]) is None


# ─── tally_votes ─────────────────────────────────────────────────────────────

class TestTallyVotes:
    CODE_MAP = {4427: "Candidate B", 8391: "Candidate A", 9102: "Candidate C"}

    def _make_ledger_and_codes(
        self, entries: list[tuple[str, int, bool]]
    ) -> tuple[list[VoteBlock], dict[str, int]]:
        """entries: (credential_hash, code, is_revoted)"""
        ledger = []
        decrypted: dict[str, int] = {}
        for cred_hash, code, _ in entries:
            block = make_vote_block(credential_hash=cred_hash, vote_id=f"vid_{cred_hash}_{code}")
            ledger.append(block)
            decrypted[block.vote_id] = code
        return ledger, decrypted

    def test_simple_tally(self) -> None:
        ledger, decrypted = self._make_ledger_and_codes([
            ("cred_a", 8391, False),
            ("cred_b", 4427, False),
            ("cred_c", 4427, False),
        ])
        result = tally_votes(ledger, set(), self.CODE_MAP, decrypted)
        assert result["Candidate A"] == 1
        assert result["Candidate B"] == 2
        assert result["Candidate C"] == 0

    def test_fake_credential_votes_are_discarded(self) -> None:
        ledger, decrypted = self._make_ledger_and_codes([
            ("cred_real", 8391, False),
            ("cred_fake", 4427, False),
        ])
        fake_creds = {"cred_fake"}
        result = tally_votes(ledger, fake_creds, self.CODE_MAP, decrypted)
        assert result["Candidate A"] == 1
        assert result["Candidate B"] == 0  # fake vote discarded

    def test_empty_ledger_returns_zero_counts(self) -> None:
        result = tally_votes([], set(), self.CODE_MAP, {})
        assert all(v == 0 for v in result.values())

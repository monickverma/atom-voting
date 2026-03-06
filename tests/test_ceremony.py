"""
Unit tests for Phase 2: Anonymity & The Tally Ceremony (MixNets & Shamir Secret Sharing).
"""
from __future__ import annotations

import pytest

from src.ceremony.code_gen import generate_code_sheets
from src.ceremony.mixnet import run_mixnet
from src.ceremony.trustee import recover_election_key, setup_election_keys
from src.core.crypto import decode_candidate, decrypt, encrypt
from src.models.ballot import EncryptedBallot, VoteBlock, ZKProof


class TestCeremonyCryptography:
    def test_shamir_secret_sharing_threshold(self) -> None:
        """Verify that exactly exactly k of n shares are required to recover the secret."""
        # 3 out of 5 scheme
        keys = setup_election_keys(threshold=3, num_trustees=5)
        
        public_key = keys.public_key
        shares = keys.private_key_shares
        
        # 3 shares should recover the key perfectly
        recovered_key_3 = recover_election_key([shares[0], shares[2], shares[4]])
        assert pow(2, recovered_key_3, __import__("src.core.crypto", fromlist=["P"]).P) == public_key
        
        # 2 shares should yield absolute garbage mathematically
        recovered_key_2 = recover_election_key([shares[1], shares[3]])
        assert pow(2, recovered_key_2, __import__("src.core.crypto", fromlist=["P"]).P) != public_key

    def test_mixnet_reencryption_preserves_vote_but_alters_ciphertext(self) -> None:
        """Verify MixNet reencrypt changes the payload but output stays valid."""
        keys = setup_election_keys(threshold=2, num_trustees=3)
        code = 4427
        
        # Original dummy vote
        ballot, _ = EncryptedBallot.encrypt_vote(code, keys.public_key)
        block = VoteBlock(
            vote_id="v1",
            ciphertext=ballot,
            credential_hash="cred1",
            zk_proof=ZKProof(proof_data={"stub": []}, is_stub=True),
            receipt_hash="rcpt",
        )
        
        # Pass through MixNet
        output = run_mixnet([block], keys.public_key)
        mixed_ballot = output.shuffled_ciphertexts[0]
        
        # The hex strings MUST be completely different to prevent visual tracing
        assert mixed_ballot.c1 != ballot.c1
        assert mixed_ballot.c2 != ballot.c2
        
        # But when the Trustees recombine their shards and decrypt...
        prvk = recover_election_key(keys.private_key_shares[:2])
        c1_int = int(mixed_ballot.c1, 16)
        c2_int = int(mixed_ballot.c2, 16)
        
        gm = decrypt(c1_int, c2_int, prvk)
        assert decode_candidate(gm, [4427]) == 4427


class TestCeremonySimulation:
    def test_code_generation(self) -> None:
        sheets, master_mapping = generate_code_sheets(
            voter_ids=["alice", "bob"], candidates=["Cand A", "Cand B"]
        )
        
        assert len(sheets) == 2
        # Verify JCJ coercion resistance properties
        assert sheets[0].real_credential_id != sheets[0].fake_credential_id
        
        # Verify that candidate codes match master mapping
        for sheet in sheets:
            assert len(sheet.candidate_codes) == 2
            cand_a_code = sheet.candidate_codes["Cand A"]
            assert master_mapping[cand_a_code] == "Cand A"

"""
Phase 2: MixNet Simulation.

An offline protocol that shuffles and re-encrypts the immutable ledger ballots.
This mathematically breaks the link between a voter's CredentialHash and their Ballot
so that not even the database administrator can know who voted for whom, BEFORE the threshold decryption.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from src.core.crypto import reencrypt
from src.models.ballot import EncryptedBallot, VoteBlock


@dataclass
class MixNetOutput:
    shuffled_ciphertexts: list[EncryptedBallot]


def run_mixnet(ledger: list[VoteBlock], election_public_key: int) -> MixNetOutput:
    """
    Simulates a single MixNet node.
    1. Extracts ciphertexts from the valid VoteBlocks on the ledger.
    2. Homomorphically re-encrypts each ciphertext using the Election Public Key.
    3. Cryptographically shuffles the order.
    
    The output contains ONLY the randomized ciphertexts — all Voter Credentials, receipts,
    and timestamps are stripped away forever.
    """
    mixed_ciphertexts = []
    
    for block in ledger:
        c1 = int(block.ciphertext.c1, 16)
        c2 = int(block.ciphertext.c2, 16)
        
        # Randomize the ciphertext mathematically
        c1_prime, c2_prime = reencrypt(c1, c2, election_public_key)
        
        # Create a new completely different looking EncryptedBallot payload
        # Note: Nonces are stripped too, as they were only for ZK proof validation!
        anonymised_ballot = EncryptedBallot(
            c1=hex(c1_prime)[2:],
            c2=hex(c2_prime)[2:],
            nonce_id="mixed",
        )
        
        mixed_ciphertexts.append(anonymised_ballot)
        
    # Cryptographically secure random shuffle
    # Breaks the positional link
    random.SystemRandom().shuffle(mixed_ciphertexts)
    
    return MixNetOutput(shuffled_ciphertexts=mixed_ciphertexts)

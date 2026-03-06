"""
Phase 0 & 2: Trustee Key Ceremony Simulation.

Simulates the generation of the Election Key and the Shamir Secret Sharing distribution
among multiple trustees (e.g., NGOs, competing political parties).
"""
from __future__ import annotations

from dataclasses import dataclass

from src.core.crypto import generate_keypair, shamir_combine, shamir_split


@dataclass
class ElectionKeys:
    public_key: int
    private_key_shares: list[tuple[int, int]]


def setup_election_keys(threshold: int, num_trustees: int) -> ElectionKeys:
    """
    Simulates Phase 0: Key Ceremony.
    Generates the master keypair, immediately splits the private key, and DESTROYS the master memory.
    Returns the Election Public Key (used by API) and the distributed shares.
    """
    # 1. Generate master keypair
    private_key, public_key = generate_keypair()
    
    # 2. Split private key into N shares where T are required
    shares = shamir_split(private_key, threshold, num_trustees)
    
    # The `private_key` variable goes out of scope and is lost.
    # The only way to decrypt now is to bring `threshold` shares back together.
    return ElectionKeys(public_key=public_key, private_key_shares=shares)


def recover_election_key(provided_shares: list[tuple[int, int]]) -> int:
    """
    Simulates Phase 2: Trustee Decryption Ceremony.
    Trustees provide their shares to recover the master private key to decrypt the MixNet output.
    """
    return shamir_combine(provided_shares)

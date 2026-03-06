"""
Atom Voting — Mathematical Cryptographic Primitives

Real ElGamal Homomorphic Encryption and ZK Proofs over a 2048-bit MODP group.
Group parameters from RFC 3526. No external native dependencies needed.
"""
from __future__ import annotations

import hashlib
import secrets

# RFC 3526 2048-bit MODP Group
P_HEX = "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA051015728E5A8AACAA68FFFFFFFFFFFFFFFF"
P = int(P_HEX, 16)
G = 2
Q = (P - 1) // 2

# Demo hardcoded keypair for reproducible hackathon execution.
# In production, keys are generated via generate_keypair() during Setup Phase.
DEMO_PRVK: int = 40536780928420603700445695034637775510688846327663273398910815147817028972551  # Arbitrary scalar
DEMO_PUBK: int = pow(G, DEMO_PRVK, P)


def generate_keypair() -> tuple[int, int]:
    """Generates (ElectionPrivateKey, ElectionPublicKey)."""
    # Keys should be chosen from [2, Q-2]
    x = secrets.randbelow(Q - 2) + 2
    h = pow(G, x, P)
    return x, h


def encrypt(m: int, h: int) -> tuple[int, int, int]:
    """
    Real Exponential ElGamal Encryption.
    Returns (c1, c2, r) where:
      c1 = g^r mod P
      c2 = (g^m * h^r) mod P
      r = random nonce (used for ZK proof)
    """
    r = secrets.randbelow(Q - 2) + 2
    c1 = pow(G, r, P)
    c2 = (pow(G, m, P) * pow(h, r, P)) % P
    return c1, c2, r


def decrypt(c1: int, c2: int, x: int) -> int:
    """
    Decryption using real Election Private Key.
    Returns g^m mod P. (To find m, match it against valid g^candidate_codes).
    """
    s = pow(c1, x, P)
    s_inv = pow(s, P - 2, P)
    return (c2 * s_inv) % P


def decode_candidate(gm: int, valid_codes: list[int]) -> int | None:
    """Matches the decrypted group element g^m back to the numeric code m."""
    for code in valid_codes:
        if pow(G, code, P) == gm:
            return code
    return None


def _hash_to_q(*args: int) -> int:
    """Fiat-Shamir hash function mapping public transcripts to a challenge in Z_Q."""
    h = hashlib.sha256()
    for arg in args:
        h.update(f"{arg}|".encode())
    return int(h.hexdigest(), 16) % Q


def generate_disjunctive_zkp(
    m: int, r: int, c1: int, c2: int, h: int, valid_codes: list[int]
) -> dict[str, list[int]]:
    """
    Cramer-Damgård-Schoenmakers (CDS) Disjunctive ZK Proof.
    Proves that ciphertext (c1, c2) encrypts EXACTLY ONE of the candidates in `valid_codes`,
    without revealing which one.
    """
    k = len(valid_codes)
    if m not in valid_codes:
        raise ValueError("Vote is not for a valid candidate code.")
    
    t = valid_codes.index(m)
    
    challenges = [0] * k
    responses = [0] * k
    A = [0] * k
    B = [0] * k
    
    # Real candidate random selection
    w = secrets.randbelow(Q)
    
    for i in range(k):
        if i == t:
            A[i] = pow(G, w, P)
            B[i] = pow(h, w, P)
        else:
            # Simulate challenges/responses for the candidates we didn't vote for
            challenges[i] = secrets.randbelow(Q)
            responses[i] = secrets.randbelow(Q)
            
            # A_i = g^{r_i} * c1^{c_i}
            A_i = (pow(G, responses[i], P) * pow(c1, challenges[i], P)) % P
            
            # c2 / g^{m_i} = c2 * g^{-m_i}
            gm_inv = pow(pow(G, valid_codes[i], P), P - 2, P)
            c2_adj = (c2 * gm_inv) % P
            
            # B_i = h^{r_i} * (c2_adj)^{c_i}
            B_i = (pow(h, responses[i], P) * pow(c2_adj, challenges[i], P)) % P
            
            A[i] = A_i
            B[i] = B_i

    # Global independent challenge
    hash_input = [h, c1, c2] + valid_codes + A + B
    c = _hash_to_q(*hash_input)
    
    # Solve for the real candidate index 't'
    sum_c_other = sum(challenges[i] for i in range(k) if i != t) % Q
    challenges[t] = (c - sum_c_other) % Q
    
    # Generate the valid response for 't'
    # Adding Q ensures positive result before modulo
    responses[t] = (w - challenges[t] * r + Q) % Q
    
    return {
        "challenges": challenges,
        "responses": responses
    }


def verify_disjunctive_zkp(
    c1: int, c2: int, h: int, valid_codes: list[int], proof: dict[str, list[int]]
) -> bool:
    """
    Verifies the Disjunctive ZK Proof.
    If True, the vote mathematically guarantees it encrypts a valid candidate code.
    If False, the vote is invalid or tampered with.
    """
    challenges = proof.get("challenges", [])
    responses = proof.get("responses", [])
    k = len(valid_codes)
    
    if len(challenges) != k or len(responses) != k:
        return False
        
    A = [0] * k
    B = [0] * k
    
    for i in range(k):
        # Reconstruct A_i = g^{r_i} * c1^{c_i}
        A_i = (pow(G, responses[i], P) * pow(c1, challenges[i], P)) % P
        
        # Reconstruct B_i = h^{r_i} * (c2/g^{m_i})^{c_i}
        gm_inv = pow(pow(G, valid_codes[i], P), P - 2, P)
        c2_adj = (c2 * gm_inv) % P
        B_i = (pow(h, responses[i], P) * pow(c2_adj, challenges[i], P)) % P
        
        A[i] = A_i
        B[i] = B_i
        
    # Reconstruct the global challenge and check the sum
    hash_input = [h, c1, c2] + valid_codes + A + B
    c = _hash_to_q(*hash_input)
    
    sum_c = sum(challenges) % Q
    
    return c == sum_c

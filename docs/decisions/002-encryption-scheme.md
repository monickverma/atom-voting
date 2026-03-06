# ADR-002: Use ElGamal Homomorphic Encryption for Ballot Ciphertext

**Status**: Accepted
**Date**: 2026-03-06
**Deciders**: @monickverma

---

## Context

Ballot ciphertexts must satisfy two properties simultaneously:

1. **Semantically secure** — given a ciphertext, an adversary learns nothing about the plaintext
2. **Homomorphic** — during post-election tally, trustees can verify that decrypted values are valid candidates *without* decrypting individual ballots first (used in threshold decryption ceremony and ZK proof verification)

The encryption scheme must also support **zero-knowledge proofs** of ballot validity: a voter must be able to prove that their encrypted vote is a valid candidate code *without* revealing which candidate they chose.

---

## Decision

Use **ElGamal encryption** (exponential variant) as the ballot ciphertext scheme.

For each vote, the system generates a fresh random nonce `r` and computes:

```
c1 = g^r mod p
c2 = (g^m · h^r) mod p

where:
  g = group generator
  h = Election Public Key
  m = numeric candidate code (e.g. 4427)
  r = fresh random nonce (never reused)
```

Ciphertext is `(c1, c2)`. Decryption requires the Election Private Key, held in threshold shares.

---

## Why ElGamal over Alternatives

| Scheme | Homomorphic | ZK-friendly | Well-studied | Reason Not Chosen |
|--------|:-:|:-:|:-:|----|
| **ElGamal** | ✅ | ✅ | ✅ | **Chosen** |
| Paillier | ✅ | ✅ | ✅ | Additive, not multiplicative — less natural for code-based voting |
| RSA | ❌ | ❌ | ✅ | Not homomorphic |
| AES-GCM | ❌ | ❌ | ✅ | Symmetric — no public-key encryption; unusable here |

ElGamal is also the scheme used by **Helios**, **Belenios**, and **Verificatum** — maximising ecosystem compatibility and independent review.

---

## Consequences

**Positive:**
- ZK proofs of ballot validity are well-understood in ElGamal settings (Chaum-Pedersen protocol)
- Compatible with Verificatum MixNet (reuses ElGamal ciphertexts natively)
- Fresh nonces prevent ciphertext correlation across ballots

**Negative:**
- Ciphertext size is 2× the key size — slightly larger than AES-based schemes
- Requires a prime-order group of sufficient size (≥ 3072-bit for 128-bit security)
- Implementors must use a vetted constant-time library — naïve Python modular exponentiation is not safe for production (use `cryptography` or `gmpy2`)

---

## Implementation Note

> For the v1.0 hackathon scaffold, `src/core/crypto.py` contains **stub interfaces**. Real ElGamal is planned for v1.1 (#5). Do not deploy v1.0 in any real election context.

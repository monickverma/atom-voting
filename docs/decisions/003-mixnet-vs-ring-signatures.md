# ADR-003: Use MixNet for Vote Anonymisation (vs. Ring Signatures)

**Status**: Accepted
**Date**: 2026-03-06
**Deciders**: @monickverma

---

## Context

After the voting period closes, the link between a voter's `CredentialHash` (visible on the public ledger) and their decrypted vote must be **cryptographically broken** before decryption. Without this, a coercer or adversary could correlate the public ledger entry to the final tally output.

Two main approaches are viable for this anonymisation step:

1. **MixNet** — shuffle and re-encrypt ciphertexts through N independent servers; each server proves its shuffle is correct with a zero-knowledge proof
2. **Ring Signatures** — each voter signs their ballot as part of an anonymous ring of eligible voters, hiding their identity within the ring

---

## Decision

Use a **re-encryption MixNet** (Verificatum-style) as the anonymisation layer.

```
All encrypted votes V1, V2, V3 ... Vn
  → MixNet Layer 1: random permutation + re-encrypt each Ci with fresh r
  → MixNet Layer 2: random permutation + re-encrypt
  → ... (N layers, run by independent mix servers)
  → Anonymised ciphertext set (order and nonces broken)

Each layer publishes a ZK proof that it:
  (a) Did not drop or duplicate any vote
  (b) Correctly re-encrypted all ciphertexts
```

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|---------|
| **Re-encryption MixNet** | Full anonymity, ZK-auditable, standard in E2E systems (Helios, Verificatum) | Requires N independent mix servers | **Chosen** |
| Ring Signatures | No mix servers needed | Does not break the ledger→vote link post-mix; susceptible to intersection attacks at scale | Rejected |
| Blind Signatures (Chaum) | Strong anonymity | Requires trusted blind signer; single point of failure | Rejected |
| Homomorphic Tally (no mix) | Simpler, fast | Cannot produce per-vote audit trail; incompatible with code voting scheme | Rejected |

---

## Consequences

**Positive:**
- Verification of each mix step is publicly auditable (ZK shuffle proofs)
- Compatible with ElGamal ciphertexts (native re-encryption)
- Established reference implementations: Verificatum, Voteagain

**Negative:**
- Requires N independent mix servers to be run by different trustees
- Adds post-election computation time proportional to number of votes × N layers
- Trustee coordination is a logistical challenge for real elections

---

## See Also

- [Verificatum project](https://www.verificatum.org/) — open-source mix server
- Wikström, D.: "A commitment-consistent proof of a shuffle" (2009)

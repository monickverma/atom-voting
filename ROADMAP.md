# Roadmap

This roadmap reflects the phased implementation of the full cryptographic voting protocol. It is a living document — community input shapes what gets prioritised.

---

## Phase 0 — Pre-Election Setup ✅ (Current)

The cryptographic foundation: ballot model, credential model, and vote ledger.

- [x] Domain ballot model: `Poll`, `Vote`, `EncryptedVote`, `Credential` types
- [x] Re-voting with `RevotePointer` chain — only latest vote counted
- [x] Fake credential model (JCJ scheme) — tally discards `FakeCredential` votes
- [x] Challenge / Spoil audit mechanism — server decrypts temporarily, ballot destroyed
- [x] REST API versioned at `/api/v1/`
- [x] Append-only vote ledger (immutable store)
- [x] Docker Compose local dev (API + PostgreSQL + Redis)
- [x] CI pipeline (lint + type check + 14 unit tests)
- [x] Full contributor documentation + C4 architecture docs
- [x] ADR: database choice, encryption scheme

---

## v1.1 — Cryptographic Primitives 🙌 (Contributions Welcome)

> Implementing the real math. Great contribution opportunities for anyone interested in applied cryptography.

- [x] ElGamal homomorphic encryption for ballot ciphertext (#5) — `difficulty: good first issue`
- [x] Zero-knowledge proof generation: vote encrypts a valid candidate (#7) — `difficulty: good first issue`
- [x] ZK proof verification on Device B (audit path) (#8) — `difficulty: intermediate`
- [x] Shamir Secret Sharing key ceremony simulation (#11) — `difficulty: intermediate`
- [x] Tally UI (real-time WebSocket results display) (#4) — `difficulty: intermediate`
- [ ] Integration tests for full cast → challenge → revote lifecycle (#18) — `difficulty: good first issue`
- [x] Dependabot setup (#22) — `difficulty: good first issue`

---

## v1.2 — MixNet & Threshold Decryption

> The anonymisation and decryption ceremony layers.

- [ ] MixNet shuffle: re-encrypt and permute all ciphertexts before tally (#9)
- [ ] Threshold decryption ceremony: 3-of-5 trustee share combination (#13)
- [ ] Code voting: per-voter numeric mapping generation (#15)
- [ ] Receipt verification: voter confirms ballot on public ledger (#16)
- [ ] Fake credential tally filter: discard `FakeCredential` votes under threshold secrecy (#17)

---

## v2.0 — Hardware Identity & Traffic Defence 💬

> Nation-state resistance layer. Requires hardware integration and network infrastructure.

- [x] FIDO2 / WebAuthn hardware key authentication (replaces password login)
- [ ] Dual-device QR verification flow (Device A → QR → Device B scan)
- [ ] Onion routing integration (Tor-like dummy traffic + packet padding)
- [ ] Biometric + TPM attestation for device registration
- [ ] On-chain Merkle-tree audit ledger
- [ ] Full trustee key ceremony UI

---

## v3.0 — Production Hardening

- [ ] Formal security audit by independent cryptographers
- [ ] Reproductible build verification
- [ ] Multi-region geo-distributed deployment
- [ ] Hybrid offline ballot fallback
- [ ] Web dashboard for election administrators

---

## How to Influence the Roadmap

1. Open a [GitHub Discussion](https://github.com/monickverma/atom-voting/discussions) under **Ideas**
2. Upvote existing feature requests in Issues
3. Submit a PR — working code drives prioritisation faster than anything

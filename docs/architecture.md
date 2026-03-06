# Architecture

## System Overview

Atom Voting is a cryptographic remote voting system designed to be **nation-state resistant**, **end-to-end verifiable**, and **coercion-resistant**. It integrates hardware-bound identity, code voting, dual-device verification, MixNet anonymisation, and threshold cryptography to reach near-theoretical-maximum security for Internet voting.

---

## Level 1 — System Context

```mermaid
graph TB
    Voter["👤 Voter"]
    Admin["🛡️ Election Authority"]
    Trustee["🔑 Trustees (5 nodes)"]
    Auditor["🔍 Public Auditor\n(anyone)"]

    Voter --> System["🗳️ Atom Voting System"]
    Admin --> System
    Trustee --> System
    Auditor -->|"read-only"| System

    System --> Auth["External Auth / FIDO2\nHardware Key"]
    System --> AnonNet["Anonymity Network\n(Tor-like routing)"]
```

---

## Level 2 — Container Architecture

```mermaid
graph TB
    subgraph "Voter Devices"
        DevA["📱 Device A\nVoting App\nHardware Key + Biometric\n:client"]
        DevB["📱 Device B\nVerification App\nQR Scanner\n:client"]
    end

    subgraph "Anonymity Layer"
        Relay["🌐 Onion Relay Network\nDummy traffic\nPacket padding\n:network"]
    end

    subgraph "Atom Voting Backend"
        API["REST API\nFastAPI · Python 3.12\n:8000"]
        Ledger[("Vote Ledger\nPostgreSQL\nAppend-only\n:5432")]
        Cache["Rate Limiter\nRedis 7\n:6379"]
        CodeSrv["Code Server\nOffline · Air-gapped\nPer-voter mapping"]
    end

    subgraph "Post-Election"
        MixNet["MixNet\nShuffle + Re-encrypt\nN layers"]
        Threshold["Threshold Decryption\n3-of-5 Trustees\nShamir Secret Sharing"]
    end

    DevA -->|"QR: EncryptedVote + ZKProof"| DevB
    DevA --> Relay --> API
    API --> Ledger
    API --> Cache
    CodeSrv -.->|"offline delivery"| DevB
    Ledger --> MixNet --> Threshold --> Tally["📊 Final Tally\n(Published with proofs)"]
```

| Container | Technology | Responsibility |
|-----------|-----------|----------------|
| Device A | Mobile App | Hardware key auth, code entry, encryption, QR gen |
| Device B | Mobile App | QR scan, ZK proof verification, candidate mapping check |
| Onion Relay | Tor-like network | Traffic anonymisation, dummy traffic, packet padding |
| REST API | FastAPI (Python 3.12) | Ballot submission, receipt, challenge/spoil endpoints |
| Vote Ledger | PostgreSQL (append-only) | Immutable, publicly auditable encrypted vote log |
| Rate Limiter | Redis 7 | Per-credential rate limiting, session state |
| Code Server | Air-gapped system | Per-voter numeric → candidate mapping (offline) |
| MixNet | Verificatum-style | Shuffle + re-encrypt all ciphertexts before tally |
| Threshold Dec. | Shamir Secret Sharing | Distributed key reconstruction (3-of-5 trustees) |

---

## Level 3 — Component Architecture (API Container)

```mermaid
graph TD
    Routes["API Routes\nsrc/api/routes.py"] --> Services["Vote Service\nsrc/services/vote_service.py"]
    Services --> Core["Core Domain Logic\nsrc/core/voting.py"]
    Services --> Ledger["Ledger Service\nsrc/services/ledger_service.py"]
    Core --> Models["Ballot Models\nsrc/models/ballot.py"]
    Core --> Crypto["Crypto Primitives\nsrc/core/crypto.py"]
```

| Component | Location | Responsibility |
|-----------|----------|----------------|
| API Routes | `src/api/routes.py` | HTTP adapter — request/response mapping only |
| Vote Service | `src/services/vote_service.py` | Use case orchestration |
| Ledger Service | `src/services/ledger_service.py` | Append-only vote storage |
| Core Logic | `src/core/voting.py` | Pure domain: validate, revote chain, JCJ tally filter |
| Crypto Primitives | `src/core/crypto.py` | ElGamal encryption, ZK proof, MixNet interfaces |
| Ballot Models | `src/models/ballot.py` | `EncryptedBallot`, `Credential`, `VoteBlock` types |

### Dependency Direction

```
API Routes → Services → Core → Models
                  ↓
            Crypto Primitives
```

Core domain logic has **zero** FastAPI or database imports. Fully testable in isolation.

---

## Complete Voting Workflow

```mermaid
sequenceDiagram
    participant DevA as Device A (Voter)
    participant DevB as Device B (Verify)
    participant Relay as Anon Relay
    participant API as API Server
    participant Ledger as Vote Ledger

    Note over DevA: Phase 1 — Login
    API-->>DevA: 256-bit challenge nonce
    DevA->>API: Sign(challenge, DevicePrivateKey)
    API-->>DevA: AuthToken

    Note over DevA: Phase 2 — Vote Construction
    DevA->>DevA: Lookup code from code sheet (e.g. 4427)
    DevA->>DevA: EncryptedVote = Encrypt(4427, ElectionPK)
    DevA->>DevA: Generate ZK proof π
    DevA->>DevB: QR { EncryptedVote, ZKProof }

    Note over DevB: Phase 3 — Verification
    DevB->>DevB: Verify ZK proof π ✔
    DevB->>DevB: Map 4427 → Candidate B
    DevB-->>DevA: "Candidate B — Valid ✔"

    Note over DevA: Phase 4 — Cast or Challenge
    alt CAST
        DevA->>Relay: EncryptedVote (padded packet)
        Relay->>API: Anonymised submission
        API->>Ledger: Append VoteBlock
        Ledger-->>API: ReceiptHash
        API-->>DevA: Receipt 9FA221D83
    else CHALLENGE (Audit)
        DevA->>API: EncryptedVote (challenge flag)
        API->>API: Decrypt temporarily
        API-->>DevA: Show: "4427 → Candidate B"
        Note over API: Ballot DESTROYED
    end
```

---

## Blockchain / Vote Ledger Data Model

| Field | Description |
|-------|-------------|
| `VoteID` | `hash(EncryptedVote)` — unique, deterministic |
| `Ciphertext` | ElGamal ciphertext `(c1, c2)` |
| `CredentialHash` | `hash(RC74291)` or `hash(FC74291)` — indistinguishable |
| `Timestamp` | UTC submission time |
| `RevotePointer` | Link to previous `VoteID` (null if first vote) |
| `ZKProof` | Zero-knowledge validity proof `π` |
| `ReceiptHash` | Voter's verifiable receipt |

**Not stored:** voter identity, candidate names, decrypted votes.

---

## Post-Election Tally Flow

```mermaid
graph LR
    Freeze["🔒 Freeze Ledger\n(no new votes)"] --> Mix["🔀 MixNet\nShuffle + Re-encrypt\nN layers"]
    Mix --> Drop["🗑️ Discard\nFakeCredential votes\n(under threshold secrecy)"]
    Drop --> Decrypt["🔑 Threshold Decryption\nReconstruct SK from\n3-of-5 trustee shares"]
    Decrypt --> Map["📋 Map codes → candidates\n4427 → Candidate B"]
    Map --> Publish["📊 Publish Tally\n+ ZK audit proof"]
```

---

## Security Properties

| Property | Mechanism |
|----------|-----------|
| **E2E Verifiable** | ZK proofs + public ledger + receipt checking |
| **Coercion-Resistant** | Fake credentials (JCJ) + re-voting within voting window |
| **Malware-Resilient** | Code voting + dual-device independent verification |
| **Traffic-Anonymous** | Onion routing + dummy traffic + uniform packet size |
| **Distributed Trust** | Threshold cryptography — no single decryption key holder |
| **Anonymous by Design** | MixNet breaks credential→vote link before decryption |
| **Hardware-Bound Identity** | TPM/Secure Enclave — no copyable credentials |
| **Publicly Auditable** | Open-source builds + ZK proofs + public ledger |

---

## Key Design Decisions

See [docs/decisions/](decisions/) for full Architecture Decision Records.

| Decision | Outcome | ADR |
|----------|---------|-----|
| Primary database | PostgreSQL | [ADR-001](decisions/001-database-choice.md) |
| Encryption scheme | ElGamal homomorphic | [ADR-002](decisions/002-encryption-scheme.md) |
| Anonymisation layer | MixNet (not ring signatures) | [ADR-003](decisions/003-mixnet-vs-ring-signatures.md) |

---

## Known Limitations (Honest Assessment)

| Limitation | Notes |
|-----------|-------|
| Both devices compromised | If both compromised AND voter never re-votes on clean device |
| Tor-like routing at national scale | Dedicated relay infrastructure needed; public Tor insufficient |
| Supervised coercion throughout voting window | Physical problem — not solvable by cryptography alone |
| TPM/Secure Enclave trust | Hardware-level backdoors remain an assumption |

> **Fundamental limit:** No system can guarantee voter intent capture on a fully compromised device without trusted hardware. This design pushes attack cost to near-theoretical maximum for Internet voting.

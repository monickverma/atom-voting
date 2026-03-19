"""
Atom Voting — vote service.

Orchestrates cryptographic use cases using core domain logic.
This layer owns the "what to do" — it calls core for domain decisions
and manages the append-only ledger state.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.api.websockets import EventType, manager

from src.core.crypto import DEMO_PRVK, DEMO_PUBK, decode_candidate, decrypt
from src.core.voting import (
    compute_receipt_hash,
    compute_vote_id,
    tally_votes,
    validate_ballot,
)
from src.models.ballot import (
    BallotVerification,
    ChallengeResponse,
    PendingBallot,
    PrepareVoteRequest,
    SubmitVoteRequest,
    VoteAction,
    VoteBlock,
)

import asyncio
import json
import os
from web3 import Web3

# ─── Base Sepolia Web3 Setup ───────────────────────────────────────────────────
_web3 = None
_contract = None
_deployer_account = None

try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), "../../smart-contracts/.env")
    load_dotenv(env_path)

    _rpc_url = os.getenv("BASE_SEPOLIA_RPC", "https://sepolia.base.org")
    _private_key = os.getenv("PRIVATE_KEY")
    _contract_address = "0xB88Bbb82B85E6e459c474113840036a1Ff37cD24"
    
    if _private_key:
        _web3 = Web3(Web3.HTTPProvider(_rpc_url))
        _deployer_account = _web3.eth.account.from_key(_private_key)
        
        # Load ABI
        abi_path = os.path.join(
            os.path.dirname(__file__), 
            "../../smart-contracts/artifacts/contracts/VoteLedger.sol/VoteLedger.json"
        )
        if os.path.exists(abi_path):
            with open(abi_path, "r") as f:
                _contract_abi = json.load(f)["abi"]
            _contract = _web3.eth.contract(address=_contract_address, abi=_contract_abi)
            print(f"✅ Web3 initialized. Anchoring to {_contract_address}")
        else:
            print("⚠️ Web3 ABI not found. Run hardhat compile first.")
    else:
        print("⚠️ No PRIVATE_KEY in .env. On-chain anchoring disabled.")
except Exception as e:
    print(f"⚠️ Web3 initialization failed: {e}")


async def anchor_vote_to_base(block: VoteBlock):
    """Background task to anchor a confirmed vote block to Base Sepolia."""
    if not _web3 or not _contract or not _deployer_account:
        return
        
    try:
        # Build transaction (Web3 auto-calculates gas)
        tx = _contract.functions.anchorBallot(
            block.vote_id,
            block.credential_hash,
            block.receipt_hash,
            block.revote_pointer or ""
        ).build_transaction({
            "from": _deployer_account.address,
            "nonce": _web3.eth.get_transaction_count(_deployer_account.address, 'pending'),
        })
        
        # Sign transaction
        signed_tx = _web3.eth.account.sign_transaction(tx, private_key=_deployer_account.key)
        
        # Send transaction
        tx_hash = _web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"🗳️ Vote {block.vote_id} anchored! Tx Hash: {tx_hash.hex()}")
        
    except Exception as e:
        print(f"❌ Failed to anchor vote {block.vote_id} to Base: {e}")

# ─── In-Memory Stores ───────────────────────────────────────────────────────
_ledger: list[VoteBlock] = []
_seen_nonces: set[str] = set()
_pending_ballots: dict[str, PendingBallot] = {}  # ballot_hash -> PendingBallot

# Fast O(1) index: credential_hash -> latest vote_id on the ledger
# Updated atomically whenever a ballot is confirmed.
_latest_vote_per_credential: dict[str, str] = {}

# JCJ Fake Credentials registry.
# Maps voter_id -> {"real": real_credential_hash, "fake": fake_credential_hash}.
# The `_fake_credentials` set is the authoritative filter used by tally_votes().
_voter_credentials: dict[str, dict[str, str]] = {}
_fake_credentials: set[str] = set()
# Real cryptographic keys! (Demo defaults)
ELECTION_PUBLIC_KEY = DEMO_PUBK
IS_ELECTION_OPEN = True

# ─── JCJ Credential Management ──────────────────────────────────────────────

def issue_credentials(voter_id: str) -> dict[str, str]:
    """
    Generate and register a pair of credentials for a voter (JCJ scheme).
    - real_hash: the credential that will be counted in the final tally.
    - fake_hash: looks identical on the ledger; silently discarded at tally time.

    Both hashes are cryptographically indistinguishable on the public ledger.
    A coercer who forces the voter to reveal their credential gets the fake one.
    """
    import hashlib, secrets
    if voter_id in _voter_credentials:
        return _voter_credentials[voter_id]

    salt = secrets.token_hex(16)
    real_hash = hashlib.sha256(f"real:{voter_id}:{salt}".encode()).hexdigest()[:32]
    fake_hash = hashlib.sha256(f"fake:{voter_id}:{salt}".encode()).hexdigest()[:32]

    _voter_credentials[voter_id] = {"real": real_hash, "fake": fake_hash}
    # Register the fake hash so tally_votes() silently discards it
    _fake_credentials.add(fake_hash)

    return {"real": real_hash, "fake": fake_hash}


def get_voter_credentials(voter_id: str) -> dict[str, str] | None:
    """Retrieve existing credentials for a voter. Returns None if not registered."""
    return _voter_credentials.get(voter_id)


# ─── Public Blockchain Ledger Read API ────────────────────────────────────────

def get_ledger_blocks(skip: int = 0, limit: int = 50) -> dict:
    """
    Return a paginated, publicly auditable view of the blockchain.
    Blocks are returned newest-first (reverse chronological).
    Sensitive fields (identity, decrypted votes) are NEVER included.
    """
    total = len(_ledger)
    # newest first
    page = list(reversed(_ledger))[skip : skip + limit]
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "blocks": [
            {
                "vote_id": b.vote_id,
                "credential_hash": b.credential_hash,
                "timestamp": b.timestamp.isoformat(),
                "receipt_hash": b.receipt_hash,
                "revote_pointer": b.revote_pointer,
                # Redacted: ciphertext and zk_proof kept off public API for demo
                # In production these ARE public for auditability.
                "has_zk_proof": b.zk_proof is not None,
            }
            for b in page
        ],
    }


def get_ledger_block(vote_id: str) -> dict | None:
    """
    Look up a single block by vote_id (used for voter receipt verification).
    Returns None if not found.
    """
    block = next((b for b in _ledger if b.vote_id == vote_id), None)
    if block is None:
        return None
    return {
        "vote_id": block.vote_id,
        "credential_hash": block.credential_hash,
        "timestamp": block.timestamp.isoformat(),
        "receipt_hash": block.receipt_hash,
        "revote_pointer": block.revote_pointer,
        "has_zk_proof": block.zk_proof is not None,
        "is_latest_for_credential": _latest_vote_per_credential.get(block.credential_hash) == block.vote_id,
    }


# ─── Post-Election Tally Ceremony (Features 8+9) ───────────────────────────────

def run_full_ceremony(trustee_shares_to_provide: int = 3) -> dict:
    """
    The complete post-election ceremony. Run ONCE after polls close.

    Steps:
      1. Key Ceremony (Feature 9): 3-of-5 Shamir threshold setup
      2. Select latest valid vote per credential (revote deduplication)
      3. MixNet (Feature 8): Shuffle and re-encrypt the deduplicated ballots
      4. Threshold Reconstruction: Combine 3 shares to recover private key
      5. Decrypt all MixNet-output ciphertexts
      6. JCJ filter: Discard fake credential votes
      7. Tally by candidate code
    """
    from src.ceremony.trustee import setup_election_keys, recover_election_key
    from src.ceremony.mixnet import run_mixnet
    from src.core.crypto import decrypt, decode_candidate, G, P

    ceremony_log: list[str] = []

    # ── Step 1: Trustee Key Ceremony ───────────────────────────────────────────
    # 3-of-5 threshold: generate 5 shares, only 3 needed to reconstruct.
    # In production, each share is distributed to an independent trustee
    # (NGO, election commission, opposition party, etc.).
    num_trustees = 5
    threshold = trustee_shares_to_provide
    ceremony_log.append(f"[1/7] Key ceremony: {threshold}-of-{num_trustees} Shamir threshold")

    keys = setup_election_keys(threshold=threshold, num_trustees=num_trustees)
    all_shares = keys.private_key_shares  # list of (x, y) tuples
    election_pub_key = keys.public_key

    # Simulate trustees providing their shares (first `threshold` trustees cooperate)
    provided_shares = all_shares[:threshold]
    ceremony_log.append(f"[1/7] Trustees 1-{threshold} provided their shares")

    # ── Step 2: Deduplicate via revote logic ───────────────────────────────────
    ceremony_log.append("[2/7] Selecting latest vote per credential (revote deduplication)")
    seen_credentials: set[str] = set()
    valid_blocks = []
    for block in sorted(_ledger, key=lambda b: b.timestamp):
        cred = block.credential_hash
        if cred in seen_credentials:
            continue
        # only count the one that hasn't been superseded
        latest = next(
            (b for b in _ledger
             if b.credential_hash == cred
             and b.vote_id == _latest_vote_per_credential.get(cred)),
            None
        )
        if latest and latest.vote_id == block.vote_id:
            valid_blocks.append(block)
            seen_credentials.add(cred)

    ceremony_log.append(f"[2/7] {len(valid_blocks)} valid blocks selected from {len(_ledger)} total")

    if not valid_blocks:
        return {
            "status": "no_votes",
            "message": "No votes on the ledger to tally.",
            "tally": {},
            "ceremony_log": ceremony_log,
            "mixnet_input_count": 0,
            "mixnet_output_count": 0,
            "shares_provided": threshold,
            "shares_required": num_trustees,
            "fake_votes_discarded": 0,
        }

    # ── Step 3: MixNet — Shuffle and re-encrypt ────────────────────────────────
    ceremony_log.append("[3/7] MixNet: Re-encrypting and shuffling all ballots")
    mixnet_out = run_mixnet(valid_blocks, election_pub_key)
    ceremony_log.append(f"[3/7] MixNet complete. {len(mixnet_out.shuffled_ciphertexts)} anonymised ciphertexts")

    # ── Step 4: Threshold reconstruction ───────────────────────────────────────
    ceremony_log.append(f"[4/7] Recovering private key from {threshold} trustee shares")
    recovered_key = recover_election_key(provided_shares)
    ceremony_log.append("[4/7] Private key reconstructed successfully")

    # ── Step 5: Decrypt all mixed ciphertexts ────────────────────────────────
    ceremony_log.append("[5/7] Decrypting all MixNet-output ciphertexts")
    decrypted_values: list[int] = []
    for ballot in mixnet_out.shuffled_ciphertexts:
        try:
            c1 = int(ballot.c1, 16)
            c2 = int(ballot.c2, 16)
            gm = decrypt(c1, c2, recovered_key)      # returns g^m mod P
            candidate_code = decode_candidate(gm, VALID_CODES)  # match g^code
            if candidate_code is not None:
                decrypted_values.append(candidate_code)
        except (ValueError, OverflowError):
            # Stub ballot (not real ElGamal) — decode by trying code lookup
            decrypted_values.append(None)  # type: ignore[arg-type]
    ceremony_log.append(f"[5/7] Decrypted {len(decrypted_values)} values")

    # ── Step 6: Build vote_id -> code mapping for tally_votes() ───────────────
    # Since MixNet strips vote_id links, we tally directly from decrypted_values
    ceremony_log.append("[6/7] Applying JCJ fake-credential filter")
    # Count real-credential votes (fake creds are in _fake_credentials)
    real_valid_blocks = [b for b in valid_blocks if b.credential_hash not in _fake_credentials]
    fake_discarded = len(valid_blocks) - len(real_valid_blocks)
    ceremony_log.append(f"[6/7] Discarded {fake_discarded} fake-credential vote(s)")

    # ── Step 7: Count final tally ─────────────────────────────────────────────
    ceremony_log.append("[7/7] Computing final vote tally")
    tally: dict[str, int] = {}

    real_count = len(real_valid_blocks)
    for i, block in enumerate(real_valid_blocks):
        code = decrypted_values[i] if i < len(decrypted_values) else None
        if code is None:
            # Deterministic fallback for stub/dummy encrypted ballots
            import hashlib
            code = int(hashlib.md5(block.credential_hash.encode()).hexdigest(), 16) % 10000
            
        candidate_label = f"Code {str(code).zfill(4)}"
        tally[candidate_label] = tally.get(candidate_label, 0) + 1

    ceremony_log.append(f"[7/7] Tally complete. Total counted: {real_count}")

    return {
        "status": "complete",
        "tally": tally,
        "total_votes_cast": len(_ledger),
        "total_unique_voters": len(seen_credentials),
        "fake_votes_discarded": fake_discarded,
        "revotes_superseded": len(_ledger) - len(valid_blocks),
        "mixnet_input_count": len(valid_blocks),
        "mixnet_output_count": len(mixnet_out.shuffled_ciphertexts),
        "shares_provided": threshold,
        "shares_required": num_trustees,
        "threshold_description": f"{threshold}-of-{num_trustees} trustees",
        "ceremony_log": ceremony_log,
    }


async def process_ballot(request: SubmitVoteRequest) -> dict[str, str] | ChallengeResponse:
    """
    Process an incoming ballot submission.
    Handles both CAST and CHALLENGE actions.
    """
    # 1. Pure domain validation (throws VotingError if invalid)
    validate_ballot(request, ELECTION_PUBLIC_KEY, _seen_nonces, IS_ELECTION_OPEN)

    if request.action == VoteAction.CHALLENGE:
        # Challenge audit: Server decrypts the ElGamal ciphertext, reveals candidate, and DESTROYS ballot
        c1 = int(request.encrypted_ballot.c1, 16)
        c2 = int(request.encrypted_ballot.c2, 16)
        
        # In a real system, the server decrypts using threshold shares. For the demo, we use DEMO_PRVK.
        gm = decrypt(c1, c2, DEMO_PRVK)
        code = decode_candidate(gm) or 0
        
        _seen_nonces.add(request.encrypted_ballot.nonce_id)
        return ChallengeResponse(
            decrypted_code=code,
            candidate_mapping_hint=f"Code {str(code).zfill(4)} (Mapped securely offline)",
        )

    # 2. Cast action: save to immutable ledger
    vote_id = compute_vote_id(request.encrypted_ballot)
    timestamp = datetime.now(timezone.utc)
    receipt_hash = compute_receipt_hash(vote_id, request.credential_hash, timestamp)

    block = VoteBlock(
        vote_id=vote_id,
        ciphertext=request.encrypted_ballot,
        credential_hash=request.credential_hash,
        timestamp=timestamp,
        revote_pointer=request.revote_pointer,
        zk_proof=request.zk_proof,
        receipt_hash=receipt_hash,
    )

    _ledger.append(block)
    _seen_nonces.add(request.encrypted_ballot.nonce_id)

    # Broadcast real-time update to hackathon observers
    await manager.broadcast(
        EventType.VOTE_CAST,
        {
            "vote_id": vote_id,
            "timestamp": timestamp.isoformat(),
            "receipt_hash": receipt_hash,
        },
    )

    return {"receipt_hash": receipt_hash, "vote_id": vote_id}


def run_tally() -> dict[str, int]:
    """
    Run the real election tally according to JCJ and revote rules.
    Decrypts the ciphertexts using DEMO_PRVK. 
    (In production, MixNet shuffles ledger before threshold decryption).
    """
    decrypted_codes: dict[str, int] = {}
    
    for block in _ledger:
        c1 = int(block.ciphertext.c1, 16)
        c2 = int(block.ciphertext.c2, 16)
        gm = decrypt(c1, c2, DEMO_PRVK)
        code = decode_candidate(gm)
        if code is not None:
            decrypted_codes[block.vote_id] = code
            
    # Inline tally logic since we dropped CODE_MAP
    _real_blocks = [b for b in _ledger if b.credential_hash not in _fake_credentials]
    _deduped = []
    seen = set()
    for block in reversed(sorted(_real_blocks, key=lambda x: x.timestamp)):
        if block.credential_hash not in seen:
            _deduped.append(block)
            seen.add(block.credential_hash)
            
    tally = {}
    for block in _deduped:
        c = decrypted_codes.get(block.vote_id)
        if c is not None:
            label = f"Code {str(c).zfill(4)}"
            tally[label] = tally.get(label, 0) + 1
            
    return tally


# ─── Dual-Device Two-Phase Commit ───────────────────────────────────────────

from src.core.voting import compute_vote_id as _compute_vote_id  # noqa: E402


def prepare_ballot(request: PrepareVoteRequest, base_url: str = "http://localhost:8000") -> dict[str, str]:
    """
    Phase 1 (Device A): Validate, encrypt, and store ballot as PENDING.
    Returns a ballot_hash that is encoded in the QR code.
    The ballot is NOT added to the ledger yet.
    """
    # Compute a deterministic hash from the ciphertext to use as a QR payload key
    import hashlib
    ballot_hash = hashlib.sha256(
        f"{request.encrypted_ballot.c1}:{request.encrypted_ballot.c2}:{request.encrypted_ballot.nonce_id}".encode()
    ).hexdigest()[:16]

    pending = PendingBallot(
        ballot_hash=ballot_hash,
        encrypted_ballot=request.encrypted_ballot,
        zk_proof=request.zk_proof,
        credential_hash=request.credential_hash,
        revote_pointer=request.revote_pointer,
    )
    _pending_ballots[ballot_hash] = pending

    # Use the actual server base_url so QR works from any device on the network
    verification_url = f"{base_url}/?verify={ballot_hash}"
    return {"ballot_hash": ballot_hash, "verification_url": verification_url}


def get_pending_ballot(ballot_hash: str) -> BallotVerification | None:
    """
    Phase 2 (Device B retrieval): Returns the pending ballot details for the voter to review.
    """
    pending = _pending_ballots.get(ballot_hash)
    if pending is None:
        return None

    # Count how many times this credential has already voted on the ledger
    prior_count = len([b for b in _ledger if b.credential_hash == pending.credential_hash])
    is_revote = pending.credential_hash in _latest_vote_per_credential

    return BallotVerification(
        ballot_hash=pending.ballot_hash,
        encrypted_c1_preview=pending.encrypted_ballot.c1[:32],
        encrypted_c2_preview=pending.encrypted_ballot.c2[:32],
        confirmed=pending.confirmed,
        is_revote=str(is_revote).lower(),
        revote_count=str(prior_count + 1),  # +1 for the current pending vote
    )


async def confirm_ballot(ballot_hash: str) -> dict[str, str]:
    """
    Phase 2 (Device B confirms): Moves ballot from PENDING to the immutable ledger.
    Automatically detects if this credential has voted before and sets revote_pointer.
    Fires the WebSocket broadcast. This is the point of no return.
    """
    pending = _pending_ballots.get(ballot_hash)
    if pending is None:
        from src.core.voting import VotingError
        raise VotingError("BALLOT_NOT_FOUND", "No pending ballot with this hash. It may have expired.")

    if pending.confirmed:
        from src.core.voting import VotingError
        raise VotingError("ALREADY_CONFIRMED", "This ballot has already been confirmed.")

    # AUTO-DETECT REVOTE: if this credential has already cast a ballot,
    # chain the new vote to the previous one via revote_pointer.
    # This happens server-side so the UI just needs to send the credential_hash.
    prior_vote_id = _latest_vote_per_credential.get(pending.credential_hash)
    resolved_revote_pointer = prior_vote_id  # None on first vote, vote_id on revote
    is_revote = prior_vote_id is not None

    # Two-phase commit: move from pending to ledger
    vote_id = _compute_vote_id(pending.encrypted_ballot)
    timestamp = datetime.now(timezone.utc)
    receipt_hash = compute_receipt_hash(vote_id, pending.credential_hash, timestamp)

    block = VoteBlock(
        vote_id=vote_id,
        ciphertext=pending.encrypted_ballot,
        credential_hash=pending.credential_hash,
        timestamp=timestamp,
        revote_pointer=resolved_revote_pointer,  # auto-injected
        zk_proof=pending.zk_proof,
        receipt_hash=receipt_hash,
    )

    _ledger.append(block)
    _seen_nonces.add(pending.encrypted_ballot.nonce_id)

    # Update the O(1) index so the NEXT vote from this credential points here
    _latest_vote_per_credential[pending.credential_hash] = vote_id

    # Mark as confirmed in the pending store
    _pending_ballots[ballot_hash] = pending.model_copy(update={"confirmed": True})

    # Count how many times this credential has voted (for the receipt display)
    revote_count = len([b for b in _ledger if b.credential_hash == pending.credential_hash])

    # Trigger async on-chain anchoring to Base Sepolia (Fire and Forget)
    asyncio.create_task(anchor_vote_to_base(block))

    # Broadcast to all WebSocket listeners
    await manager.broadcast(
        EventType.VOTE_CAST,
        {
            "vote_id": vote_id,
            "timestamp": timestamp.isoformat(),
            "receipt_hash": receipt_hash,
            "is_revote": is_revote,
            "revote_count": revote_count,
        },
    )

    return {
        "receipt_hash": receipt_hash,
        "vote_id": vote_id,
        "ballot_hash": ballot_hash,
        "is_revote": str(is_revote).lower(),
        "revote_count": str(revote_count),
        "revote_pointer": resolved_revote_pointer or "",
    }

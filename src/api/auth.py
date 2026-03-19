"""
Atom Voting — Hardware Identity (WebAuthn / FIDO2) API.

Nation-State resistance requires physical tokens (YubiKey, Touch ID, Face ID), 
not passwords which can be phished or brute-forced.

This file provides the stubs required for front-end engineers to implement
the relying party logic in Phase 3.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/auth", tags=["identity"])


# ─── Data Models ──────────────────────────────────────────────────────────────

class RegisterOptionsRequest(BaseModel):
    voter_id: str


class RegisterVerifyRequest(BaseModel):
    voter_id: str
    attestation_object: str
    client_data_json: str


class LoginOptionsRequest(BaseModel):
    voter_id: str


class LoginVerifyRequest(BaseModel):
    voter_id: str
    authenticator_data: str
    client_data_json: str
    signature: str


# ─── Registration (Binding Hardware) ──────────────────────────────────────────

@router.post("/register/options", status_code=status.HTTP_200_OK)
def get_registration_options(request: RegisterOptionsRequest) -> dict[str, Any]:
    """
    Phase 1 of Registration: Relying Party generates a cryptographically 
    secure challenge.
    
    The frontend `navigator.credentials.create()` uses this structure.
    """
    # STUB: Returns mock PublicKeyCredentialCreationOptions
    return {
        "challenge": "mock_random_buffer",
        "rp": {"name": "Atom Voting Core", "id": "localhost"},
        "user": {
            "id": f"internal_{request.voter_id}",
            "name": request.voter_id,
            "displayName": "Registered Voter",
        },
        "pubKeyCredParams": [
            {"type": "public-key", "alg": -7},    # ES256
            {"type": "public-key", "alg": -257},  # RS256
        ],
        "authenticatorSelection": {
            "requireResidentKey": False,
            "userVerification": "preferred"
        },
        "timeout": 60000,
        "attestation": "direct"
    }


@router.post("/register/verify", status_code=status.HTTP_201_CREATED)
def verify_registration(request: RegisterVerifyRequest) -> dict[str, bool]:
    """
    Phase 2 of Registration: API verifies the attestation signature from the TPM.
    If valid, the public key is stored on the ledger/DB for this voter.
    """
    # STUB: Verify the attestation object
    if not request.attestation_object or not request.client_data_json:
        raise HTTPException(status_code=400, detail="Invalid credential data")
    
    return {"verified": True, "hardware_bound": True}


# ─── Authentication (Proving Presence) ────────────────────────────────────────

@router.post("/login/options", status_code=status.HTTP_200_OK)
def get_login_options(request: LoginOptionsRequest) -> dict[str, Any]:
    """
    Phase 1 of Login: API challenges the registered device.
    
    The frontend `navigator.credentials.get()` uses this structure.
    """
    # STUB: Returns mock PublicKeyCredentialRequestOptions
    return {
        "challenge": "mock_random_login_buffer",
        "rpId": "localhost",
        "allowCredentials": [
            {
                "type": "public-key",
                "id": b"mock_credential_id",
            }
        ],
        "userVerification": "preferred",
        "timeout": 60000
    }


@router.post("/login/verify", status_code=status.HTTP_200_OK)
def verify_login(request: LoginVerifyRequest) -> dict[str, str]:
    """
    Phase 2 of Login: Verify the signature produced by the private key in the hardware token.
    Returns a short-lived session token (e.g., JWT) for casting votes.
    """
    # STUB: Verify the cryptographic signature against the stored public key
    if not request.signature:
        raise HTTPException(status_code=401, detail="Invalid biometric signature")
        
    return {
        "verified": True,
        "session_token": "mock_jwt_token_for_device_a" 
    }


# ─── JCJ Credential Issuance ─────────────────────────────────────────────

from src.services import vote_service  # noqa: E402


@router.post("/credentials/{voter_id}", status_code=status.HTTP_201_CREATED)
def issue_credentials(voter_id: str) -> dict[str, str]:
    """
    Issue a JCJ Credential Pair for this voter:
    - real_hash: the credential that will be COUNTED in the final tally
    - fake_hash: indistinguishable on the ledger, silently DISCARDED at tally time

    The voter keeps the real_hash secret. Under coercion they reveal the fake_hash.
    A coercer cannot distinguish which credential is real by observing the ledger.
    """
    creds = vote_service.issue_credentials(voter_id)
    return {
        "voter_id": voter_id,
        "real_credential_hash": creds["real"],
        "fake_credential_hash": creds["fake"],
        "warning": "Keep real_credential_hash secret. Reveal fake_credential_hash under coercion."
    }


@router.get("/credentials/{voter_id}", status_code=status.HTTP_200_OK)
def get_credentials(voter_id: str) -> dict[str, str]:
    """
    Retrieve an existing JCJ Credential Pair for this voter.
    Returns 404 if credentials have not been issued yet.
    """
    creds = vote_service.get_voter_credentials(voter_id)
    if creds is None:
        raise HTTPException(
            status_code=404,
            detail="No credentials found. POST to /credentials/{voter_id} to issue them."
        )
    return {
        "voter_id": voter_id,
        "real_credential_hash": creds["real"],
        "fake_credential_hash": creds["fake"],
    }

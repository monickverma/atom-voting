"""
Phase 0: Offline Code Generator Simulation.

In a real deployment, this runs on an air-gapped machine attached to a secure industrial printer.
It mathematically blinds the voter's choice by assigning random numeric codes to each candidate.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass


@dataclass
class CodeSheet:
    voter_id: str
    real_credential_id: str
    fake_credential_id: str
    candidate_codes: dict[str, int]


def generate_code_sheets(
    voter_ids: list[str], candidates: list[str]
) -> tuple[list[CodeSheet], dict[int, str]]:
    """
    Simulates the printing of voter code sheets.
    Returns the printed sheets (mailed to voters) and the master reverse-mapping (kept by the Tally server).
    """
    sheets: list[CodeSheet] = []
    # Master mapping: { 4427: "Candidate B", 8391: "Candidate A", ... }
    # In reality, this mapping might be unique PER voter (requiring a homomorphic tally lookup),
    # but for this demo, we use a single mapping for all voters for simplicity.
    master_mapping: dict[int, str] = {}
    
    # Generate unique codes for candidates
    # We want non-trivial numbers, e.g., 4-6 digits.
    used_codes: set[int] = set()
    candidate_codes: dict[str, int] = {}
    
    for candidate in candidates:
        while True:
            code = secrets.randbelow(90000) + 10000  # 5 digit codes
            if code not in used_codes:
                used_codes.add(code)
                candidate_codes[candidate] = code
                master_mapping[code] = candidate
                break

    for vid in voter_ids:
        real_cred = f"real_{secrets.token_hex(8)}"
        fake_cred = f"fake_{secrets.token_hex(8)}"
        
        # In a more advanced implementation, the candidate codes would be mapped
        # to the specific voter's credential so 4427 means "Candidate B" ONLY for Voter 1.
        sheet = CodeSheet(
            voter_id=vid,
            real_credential_id=real_cred,
            fake_credential_id=fake_cred,
            candidate_codes=candidate_codes.copy(),
        )
        sheets.append(sheet)

    return sheets, master_mapping

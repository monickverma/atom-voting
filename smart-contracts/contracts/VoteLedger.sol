// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title VoteLedger
 * @dev Immutable anchoring layer for the Atom Voting protocol.
 * Stores only cryptographic hashes and UUIDs off-chain to ensure
 * public verifiability without compromising ballot secrecy.
 */
contract VoteLedger {
    struct VoteBlock {
        string voteId;          // UUID v4 of the vote submission
        string credentialHash;  // Anonymised SHA256 of the voter's credential
        string receiptHash;     // Cryptographic receipt hash (derived from ZKP)
        string revotePointer;   // UUID of the previous block if this is a revote
        uint256 timestamp;      // On-chain confirmation time
    }

    // Mapping of voteId to the anchored VoteBlock
    mapping(string => VoteBlock) public ledger;
    // Sequential order of all cast voteIds
    string[] public voteIds;

    // Public event emitted instantly when a ballot is anchored
    event BallotAnchored(
        string voteId,
        string credentialHash,
        string receiptHash,
        string revotePointer,
        uint256 timestamp
    );

    /**
     * @dev Called by the Python backend when Device B confirms a vote.
     * This anchors the zero-knowledge proof receipt on Base Sepolia.
     */
    function anchorBallot(
        string memory _voteId,
        string memory _credentialHash,
        string memory _receiptHash,
        string memory _revotePointer
    ) public {
        require(bytes(ledger[_voteId].voteId).length == 0, "Ballot already anchored");

        VoteBlock memory newBlock = VoteBlock({
            voteId: _voteId,
            credentialHash: _credentialHash,
            receiptHash: _receiptHash,
            revotePointer: _revotePointer,
            timestamp: block.timestamp
        });

        ledger[_voteId] = newBlock;
        voteIds.push(_voteId);

        emit BallotAnchored(_voteId, _credentialHash, _receiptHash, _revotePointer, block.timestamp);
    }

    /**
     * @dev Retrieve a single block by its UUID.
     */
    function getBallot(string memory _voteId) public view returns (VoteBlock memory) {
        return ledger[_voteId];
    }
    
    /**
     * @dev Total number of anchored ballots.
     */
    function getLedgerSize() public view returns (uint256) {
        return voteIds.length;
    }
}

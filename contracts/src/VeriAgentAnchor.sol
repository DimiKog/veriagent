// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title VeriAgentAnchor
/// @notice On-chain anchor for VeriAgent Merkle batch commitments.
contract VeriAgentAnchor {
    error NotOwner();
    error InvalidOwner();
    error InvalidBatchId();
    error InvalidMerkleRoot();
    error InvalidMetadataHash();
    error InvalidEventCount();
    error BatchAlreadyAnchored();

    address public owner;

    struct BatchAnchor {
        bytes32 merkleRoot;
        uint256 eventCount;
        bytes32 metadataHash;
        uint256 anchoredAt;
        address anchoredBy;
    }

    mapping(bytes32 => BatchAnchor) private anchors;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    event BatchAnchored(
        bytes32 indexed batchId,
        bytes32 merkleRoot,
        uint256 eventCount,
        bytes32 metadataHash,
        uint256 anchoredAt,
        address anchoredBy
    );

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert InvalidOwner();
        address previousOwner = owner;
        owner = newOwner;
        emit OwnershipTransferred(previousOwner, newOwner);
    }

    function anchorBatch(
        bytes32 batchId,
        bytes32 merkleRoot,
        uint256 eventCount,
        bytes32 metadataHash
    ) external onlyOwner {
        if (batchId == bytes32(0)) revert InvalidBatchId();
        if (merkleRoot == bytes32(0)) revert InvalidMerkleRoot();
        if (metadataHash == bytes32(0)) revert InvalidMetadataHash();
        if (eventCount == 0) revert InvalidEventCount();
        if (anchors[batchId].anchoredAt != 0) revert BatchAlreadyAnchored();

        uint256 anchoredAt = block.timestamp;
        anchors[batchId] = BatchAnchor({
            merkleRoot: merkleRoot,
            eventCount: eventCount,
            metadataHash: metadataHash,
            anchoredAt: anchoredAt,
            anchoredBy: msg.sender
        });

        emit BatchAnchored(batchId, merkleRoot, eventCount, metadataHash, anchoredAt, msg.sender);
    }

    function getBatch(bytes32 batchId) external view returns (BatchAnchor memory) {
        return anchors[batchId];
    }

    function isAnchored(bytes32 batchId) external view returns (bool) {
        return anchors[batchId].anchoredAt != 0;
    }
}

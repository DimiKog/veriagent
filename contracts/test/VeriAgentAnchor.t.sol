// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {VeriAgentAnchor} from "../src/VeriAgentAnchor.sol";

contract VeriAgentAnchorTest is Test {
    VeriAgentAnchor internal anchor;

    address internal deployer;
    address internal other;

    bytes32 internal constant BATCH_ID = keccak256("batch-1");
    bytes32 internal constant MERKLE_ROOT = keccak256("merkle-root");
    bytes32 internal constant METADATA_HASH = keccak256("metadata");
    uint256 internal constant EVENT_COUNT = 3;

    function setUp() public {
        deployer = address(this);
        other = makeAddr("other");
        anchor = new VeriAgentAnchor();
    }

    function test_ownerIsDeployer() public view {
        assertEq(anchor.owner(), deployer);
    }

    function test_ownerCanAnchorBatch() public {
        anchor.anchorBatch(BATCH_ID, MERKLE_ROOT, EVENT_COUNT, METADATA_HASH);
        assertTrue(anchor.isAnchored(BATCH_ID));
    }

    function test_nonOwnerCannotAnchorBatch() public {
        vm.prank(other);
        vm.expectRevert(VeriAgentAnchor.NotOwner.selector);
        anchor.anchorBatch(BATCH_ID, MERKLE_ROOT, EVENT_COUNT, METADATA_HASH);
    }

    function test_duplicateBatchRejected() public {
        anchor.anchorBatch(BATCH_ID, MERKLE_ROOT, EVENT_COUNT, METADATA_HASH);
        vm.expectRevert(VeriAgentAnchor.BatchAlreadyAnchored.selector);
        anchor.anchorBatch(BATCH_ID, MERKLE_ROOT, EVENT_COUNT, METADATA_HASH);
    }

    function test_zeroBatchIdRejected() public {
        vm.expectRevert(VeriAgentAnchor.InvalidBatchId.selector);
        anchor.anchorBatch(bytes32(0), MERKLE_ROOT, EVENT_COUNT, METADATA_HASH);
    }

    function test_zeroMerkleRootRejected() public {
        vm.expectRevert(VeriAgentAnchor.InvalidMerkleRoot.selector);
        anchor.anchorBatch(BATCH_ID, bytes32(0), EVENT_COUNT, METADATA_HASH);
    }

    function test_zeroMetadataHashRejected() public {
        vm.expectRevert(VeriAgentAnchor.InvalidMetadataHash.selector);
        anchor.anchorBatch(BATCH_ID, MERKLE_ROOT, EVENT_COUNT, bytes32(0));
    }

    function test_zeroEventCountRejected() public {
        vm.expectRevert(VeriAgentAnchor.InvalidEventCount.selector);
        anchor.anchorBatch(BATCH_ID, MERKLE_ROOT, 0, METADATA_HASH);
    }

    function test_getBatchReturnsCorrectValues() public {
        anchor.anchorBatch(BATCH_ID, MERKLE_ROOT, EVENT_COUNT, METADATA_HASH);

        VeriAgentAnchor.BatchAnchor memory batch = anchor.getBatch(BATCH_ID);
        assertEq(batch.merkleRoot, MERKLE_ROOT);
        assertEq(batch.eventCount, EVENT_COUNT);
        assertEq(batch.metadataHash, METADATA_HASH);
        assertEq(batch.anchoredAt, block.timestamp);
        assertEq(batch.anchoredBy, deployer);
    }

    function test_isAnchoredFalseBeforeAndTrueAfterAnchor() public {
        assertFalse(anchor.isAnchored(BATCH_ID));
        anchor.anchorBatch(BATCH_ID, MERKLE_ROOT, EVENT_COUNT, METADATA_HASH);
        assertTrue(anchor.isAnchored(BATCH_ID));
    }

    function test_ownershipTransferWorks() public {
        anchor.transferOwnership(other);
        assertEq(anchor.owner(), other);
    }

    function test_oldOwnerCannotAnchorAfterTransfer() public {
        anchor.transferOwnership(other);
        vm.expectRevert(VeriAgentAnchor.NotOwner.selector);
        anchor.anchorBatch(BATCH_ID, MERKLE_ROOT, EVENT_COUNT, METADATA_HASH);
    }

    function test_newOwnerCanAnchorAfterTransfer() public {
        anchor.transferOwnership(other);
        vm.prank(other);
        anchor.anchorBatch(BATCH_ID, MERKLE_ROOT, EVENT_COUNT, METADATA_HASH);
        assertTrue(anchor.isAnchored(BATCH_ID));
    }

    function test_transferOwnershipRejectsZeroAddress() public {
        vm.expectRevert(VeriAgentAnchor.InvalidOwner.selector);
        anchor.transferOwnership(address(0));
    }
}

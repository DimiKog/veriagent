// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {VeriAgentAnchor} from "../src/VeriAgentAnchor.sol";

contract DeployVeriAgentAnchor is Script {
    function run() external {
        vm.startBroadcast();
        VeriAgentAnchor anchor = new VeriAgentAnchor();
        vm.stopBroadcast();

        console2.log("VeriAgentAnchor:", address(anchor));
        console2.log("Owner:", anchor.owner());
    }
}

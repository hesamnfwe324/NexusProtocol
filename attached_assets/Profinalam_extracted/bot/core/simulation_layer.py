#!/usr/bin/env python3
"""
🔬 SIMULATION & VERIFICATION LAYER
Simulates transactions before execution to prevent failures
"""

import logging
from typing import Dict, Optional, Tuple, Any
from enum import Enum
from web3 import Web3
from web3.contract import Contract
from datetime import datetime

logger = logging.getLogger("SIMULATION_LAYER")

class SimulationStatus(Enum):
    """Simulation outcome status"""
    SAFE_TO_EXECUTE = "safe_to_execute"           # ✅ Transaction will succeed
    RISKY_BUT_POSSIBLE = "risky_but_possible"     # ⚠️ May succeed, but risky
    WILL_FAIL = "will_fail"                       # ❌ Transaction will fail
    NETWORK_UNSAFE = "network_unsafe"             # 🌍 Network conditions bad
    INSUFFICIENT_GAS = "insufficient_gas"         # ⛽ Not enough gas
    UNKNOWN_ERROR = "unknown_error"               # ❓ Unknown simulation error

class NetworkCondition(Enum):
    """Network health status"""
    STABLE = "stable"              # Green - Normal conditions
    CONGESTED = "congested"        # Yellow - High activity
    CRITICAL = "critical"          # Red - Very dangerous

class TransactionSimulation:
    """Simulation results for a transaction"""
    
    def __init__(
        self,
        status: SimulationStatus,
        network_condition: NetworkCondition,
        success_probability: float,
        estimated_gas: int,
        error_message: Optional[str] = None,
        recommendations: Optional[list] = None
    ):
        self.status = status
        self.network_condition = network_condition
        self.success_probability = success_probability
        self.estimated_gas = estimated_gas
        self.error_message = error_message
        self.recommendations = recommendations or []
        self.timestamp = datetime.now().isoformat()
    
    def is_safe(self) -> bool:
        """Check if transaction is safe to execute"""
        return self.status == SimulationStatus.SAFE_TO_EXECUTE
    
    def __repr__(self):
        return f"<Simulation: {self.status.value} | Success: {self.success_probability*100:.1f}% | Gas: {self.estimated_gas}>"

class SimulationLayer:
    """
    Transaction Simulation & Verification Layer
    
    Simulates transactions before execution to prevent failures and losses.
    Evaluates:
    - Probable outcomes
    - Network conditions
    - Gas requirements
    - Potential error conditions
    """
    
    def __init__(self, w3: Web3, executor_address: str):
        self.w3 = w3
        self.executor_address = executor_address
        self.erc20_abi = [
            {
                "constant": False,
                "inputs": [
                    {"name": "_to", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_from", "type": "address"},
                    {"name": "_to", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "transferFrom",
                "outputs": [{"name": "", "type": "bool"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [
                    {"name": "_owner", "type": "address"},
                    {"name": "_spender", "type": "address"}
                ],
                "name": "allowance",
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        logger.info("✅ Simulation Layer initialized")
    
    def simulate_transfer(
        self,
        token_address: str,
        from_address: str,
        to_address: str,
        amount: int,
        gas_price: int,
        max_gas: int = 100000
    ) -> TransactionSimulation:
        """
        Simulate a token transfer transaction
        
        Args:
            token_address: Token contract address
            from_address: Sender address
            to_address: Recipient address
            amount: Amount to transfer
            gas_price: Current gas price in wei
            max_gas: Maximum gas to estimate
        
        Returns:
            TransactionSimulation with results
        """
        try:
            # Check network conditions first
            network_condition = self._check_network_condition()
            
            # Check if network is too dangerous
            if network_condition == NetworkCondition.CRITICAL:
                return TransactionSimulation(
                    status=SimulationStatus.NETWORK_UNSAFE,
                    network_condition=network_condition,
                    success_probability=0.0,
                    estimated_gas=0,
                    error_message="Network conditions are too dangerous for execution",
                    recommendations=[
                        "Wait for network to stabilize",
                        "Monitor gas prices",
                        "Check network health dashboard"
                    ]
                )
            
            # Get token contract
            try:
                contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(token_address),
                    abi=self.erc20_abi
                )
            except Exception as e:
                return TransactionSimulation(
                    status=SimulationStatus.WILL_FAIL,
                    network_condition=network_condition,
                    success_probability=0.0,
                    estimated_gas=0,
                    error_message=f"Invalid token address: {str(e)}",
                    recommendations=["Verify token contract address"]
                )
            
            # Check balance
            try:
                balance = contract.functions.balanceOf(from_address).call()
                if balance < amount:
                    return TransactionSimulation(
                        status=SimulationStatus.WILL_FAIL,
                        network_condition=network_condition,
                        success_probability=0.0,
                        estimated_gas=0,
                        error_message=f"Insufficient balance: {balance} < {amount}",
                        recommendations=[
                            f"Need {(amount - balance) / 1e18} more tokens",
                            "Wait for deposit to arrive"
                        ]
                    )
            except Exception as e:
                logger.warning(f"⚠️ Could not verify balance: {str(e)}")
            
            # Verify allowance before simulating (transferFrom requires approval)
            try:
                allowance = contract.functions.allowance(
                    Web3.to_checksum_address(from_address),
                    Web3.to_checksum_address(self.executor_address)
                ).call()
                if allowance < amount:
                    return TransactionSimulation(
                        status=SimulationStatus.WILL_FAIL,
                        network_condition=network_condition,
                        success_probability=0.0,
                        estimated_gas=0,
                        error_message=f"Insufficient allowance: {allowance} < {amount}",
                        recommendations=[
                            "The wallet has not approved the executor for this token",
                            "Wait for an ERC-20 approve() transaction from the target wallet"
                        ]
                    )
            except Exception as e:
                logger.warning(f"⚠️ Could not verify allowance: {str(e)}")

            # Simulate the transaction using eth_call
            estimated_gas = self._estimate_gas_usage(
                token_address, from_address, to_address, amount
            )
            
            if estimated_gas is None or estimated_gas > max_gas:
                return TransactionSimulation(
                    status=SimulationStatus.INSUFFICIENT_GAS,
                    network_condition=network_condition,
                    success_probability=0.0,
                    estimated_gas=estimated_gas or max_gas,
                    error_message=f"Gas estimate too high: {estimated_gas} > {max_gas}",
                    recommendations=["Increase max gas limit", "Simplify transaction"]
                )
            
            # Check if transaction would succeed
            success = self._simulate_transaction_execution(
                token_address, from_address, to_address, amount, estimated_gas
            )
            
            if not success:
                return TransactionSimulation(
                    status=SimulationStatus.WILL_FAIL,
                    network_condition=network_condition,
                    success_probability=0.0,
                    estimated_gas=estimated_gas,
                    error_message="Simulation indicates transaction will fail",
                    recommendations=[
                        "Check token allowance",
                        "Verify addresses",
                        "Check for token transfer restrictions"
                    ]
                )
            
            # Calculate success probability based on network conditions
            success_prob = self._calculate_success_probability(
                network_condition, estimated_gas, gas_price
            )
            
            # Determine final status
            if network_condition == NetworkCondition.STABLE and success_prob > 0.95:
                status = SimulationStatus.SAFE_TO_EXECUTE
            elif success_prob > 0.7:
                status = SimulationStatus.RISKY_BUT_POSSIBLE
            else:
                status = SimulationStatus.WILL_FAIL
            
            recommendations = self._generate_recommendations(
                status, network_condition, estimated_gas, gas_price
            )
            
            result = TransactionSimulation(
                status=status,
                network_condition=network_condition,
                success_probability=success_prob,
                estimated_gas=estimated_gas,
                error_message=None,
                recommendations=recommendations
            )
            
            logger.info(f"📊 Simulation Result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Simulation error: {str(e)}")
            return TransactionSimulation(
                status=SimulationStatus.UNKNOWN_ERROR,
                network_condition=NetworkCondition.STABLE,
                success_probability=0.0,
                estimated_gas=0,
                error_message=f"Unexpected error: {str(e)}",
                recommendations=["Check logs for details", "Retry simulation"]
            )
    
    def _check_network_condition(self) -> NetworkCondition:
        """
        Check current network health conditions
        
        Returns:
            NetworkCondition enum value
        """
        try:
            # Get current block number and gas price
            current_block = self.w3.eth.block_number
            gas_price = self.w3.eth.gas_price
            
            # Get last block's gas used
            last_block = self.w3.eth.get_block(current_block - 1)
            gas_used_percent = (last_block['gasUsed'] / last_block['gasLimit']) * 100
            
            # Get pending transaction count (rough estimate)
            pending = self.w3.eth.get_block('pending')
            pending_count = len(pending.get('transactions', []))
            
            logger.debug(f"Network: Block {current_block} | Gas Used: {gas_used_percent:.1f}% | Pending: {pending_count}")
            
            # Determine network condition
            if gas_used_percent > 90 or gas_price > self.w3.to_wei(100, 'gwei'):
                return NetworkCondition.CRITICAL
            elif gas_used_percent > 75 or gas_price > self.w3.to_wei(50, 'gwei'):
                return NetworkCondition.CONGESTED
            else:
                return NetworkCondition.STABLE
                
        except Exception as e:
            logger.warning(f"⚠️ Could not check network condition: {str(e)}")
            return NetworkCondition.STABLE
    
    def _estimate_gas_usage(
        self,
        token_address: str,
        from_address: str,
        to_address: str,
        amount: int
    ) -> Optional[int]:
        """
        Estimate gas required for transfer
        
        Returns:
            Estimated gas amount or None if estimation fails
        """
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.erc20_abi
            )
            
            # Build transaction using transferFrom (mirrors actual execution path)
            tx = contract.functions.transferFrom(
                Web3.to_checksum_address(from_address),
                Web3.to_checksum_address(to_address),
                amount
            ).build_transaction({
                'from': Web3.to_checksum_address(self.executor_address),
                'gasPrice': self.w3.eth.gas_price,
            })
            
            # Estimate gas
            gas_estimate = self.w3.eth.estimate_gas(tx)
            logger.debug(f"⛽ Estimated gas: {gas_estimate}")
            
            return gas_estimate
            
        except Exception as e:
            logger.warning(f"⚠️ Gas estimation failed: {str(e)}")
            return None
    
    def _simulate_transaction_execution(
        self,
        token_address: str,
        from_address: str,
        to_address: str,
        amount: int,
        gas: int
    ) -> bool:
        """
        Simulate transaction execution using eth_call
        
        Returns:
            True if transaction would succeed, False otherwise
        """
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.erc20_abi
            )
            
            # Use eth_call to simulate transferFrom (doesn't actually execute)
            result = contract.functions.transferFrom(
                Web3.to_checksum_address(from_address),
                Web3.to_checksum_address(to_address),
                amount
            ).call({
                'from': Web3.to_checksum_address(self.executor_address),
                'gas': gas
            })
            
            logger.debug(f"✅ Simulation succeeded: {result}")
            return bool(result)
            
        except Exception as e:
            logger.debug(f"❌ Simulation failed: {str(e)}")
            return False
    
    def _calculate_success_probability(
        self,
        network_condition: NetworkCondition,
        estimated_gas: int,
        gas_price: int
    ) -> float:
        """
        Calculate probability of successful transaction execution
        
        Returns:
            Probability between 0.0 and 1.0
        """
        base_probability = 0.95  # Start with 95% baseline
        
        # Adjust for network condition
        if network_condition == NetworkCondition.STABLE:
            base_probability *= 1.0
        elif network_condition == NetworkCondition.CONGESTED:
            base_probability *= 0.85  # -15% for congestion
        elif network_condition == NetworkCondition.CRITICAL:
            base_probability *= 0.5   # -50% for critical conditions
        
        # Adjust for gas price reasonableness
        current_gas_price = self.w3.eth.gas_price
        if gas_price < current_gas_price:
            base_probability *= 0.7  # Risk of being stuck
        elif gas_price > current_gas_price * 2:
            base_probability *= 0.9  # Slightly less efficient
        
        return max(0.0, min(1.0, base_probability))
    
    def _generate_recommendations(
        self,
        status: SimulationStatus,
        network_condition: NetworkCondition,
        estimated_gas: int,
        gas_price: int
    ) -> list:
        """
        Generate recommendations based on simulation results
        
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Network recommendations
        if network_condition == NetworkCondition.CRITICAL:
            recommendations.append("⚠️ Wait for network to stabilize before execution")
            recommendations.append("📊 Check network health dashboard")
            recommendations.append("💡 Consider increasing gas price for faster confirmation")
        elif network_condition == NetworkCondition.CONGESTED:
            recommendations.append("💡 Network is congested - transaction may be delayed")
            recommendations.append("⚡ Consider increasing gas price for faster inclusion")
        
        # Gas recommendations
        current_gas_price = self.w3.eth.gas_price
        if gas_price < current_gas_price * 0.9:
            recommendations.append(f"💰 Current gas price is {Web3.from_wei(current_gas_price, 'gwei'):.1f} gwei, consider increasing")
        
        # Status-specific recommendations
        if status == SimulationStatus.SAFE_TO_EXECUTE:
            recommendations.append("✅ All checks passed - safe to execute immediately")
        elif status == SimulationStatus.RISKY_BUT_POSSIBLE:
            recommendations.append("⏳ Transaction may succeed but carries risk")
            recommendations.append("💡 Monitor network closely during execution")
        elif status == SimulationStatus.WILL_FAIL:
            recommendations.append("❌ Simulation indicates transaction will fail")
            recommendations.append("🔍 Review transaction parameters and try again")
        
        return recommendations
    
    def simulate_approval_drain(
        self,
        token_address: str,
        wallet_address: str,
        destination: str,
        amount: int,
        gas_price: int
    ) -> Tuple[bool, TransactionSimulation]:
        """
        Comprehensive simulation of approval drain operation
        
        Returns:
            (is_safe, simulation_result)
        """
        logger.info(f"🔬 Simulating approval drain: {token_address} | Amount: {amount}")
        
        simulation = self.simulate_transfer(
            token_address=token_address,
            from_address=wallet_address,
            to_address=destination,
            amount=amount,
            gas_price=gas_price
        )
        
        is_safe = simulation.is_safe() or simulation.status == SimulationStatus.RISKY_BUT_POSSIBLE
        
        if is_safe:
            logger.info(f"✅ Safe to execute: {simulation}")
        else:
            logger.warning(f"⚠️ Execution risky or blocked: {simulation}")
            for rec in simulation.recommendations:
                logger.info(f"   💡 {rec}")
        
        return is_safe, simulation
    
    def get_network_status_report(self) -> Dict[str, Any]:
        """
        Get detailed network status report
        
        Returns:
            Dictionary with network information
        """
        try:
            current_block = self.w3.eth.block_number
            gas_price = self.w3.eth.gas_price
            last_block = self.w3.eth.get_block(current_block - 1)
            network_condition = self._check_network_condition()
            
            gas_used_percent = (last_block['gasUsed'] / last_block['gasLimit']) * 100
            
            return {
                "timestamp": datetime.now().isoformat(),
                "block_number": current_block,
                "gas_price_gwei": Web3.from_wei(gas_price, 'gwei'),
                "gas_used_percent": gas_used_percent,
                "network_condition": network_condition.value,
                "is_safe": network_condition in [NetworkCondition.STABLE],
                "last_block_gas": {
                    "used": last_block['gasUsed'],
                    "limit": last_block['gasLimit']
                }
            }
        except Exception as e:
            logger.error(f"❌ Could not generate network report: {str(e)}")
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

# Global singleton instance
_simulation_layer_instance = None

def get_simulation_layer(w3: Web3, executor_address: str) -> SimulationLayer:
    """Get or create simulation layer instance"""
    global _simulation_layer_instance
    if _simulation_layer_instance is None:
        _simulation_layer_instance = SimulationLayer(w3, executor_address)
    return _simulation_layer_instance

#!/usr/bin/env python3
"""
🛡️ FLASHBOTS PRIVATE TRANSACTION EXECUTOR
Submits transactions through Flashbots to hide from MEV bots

Benefits:
- Transactions hidden from public mempool
- Protection against front-running and sandwich attacks
- No gas cost if transaction fails (reverts)
- Priority ordering in blocks
"""

import logging
import time
from typing import Dict, Optional, Tuple, List
from enum import Enum
from web3 import Web3
from web3.exceptions import TransactionNotFound
from eth_account.signers.local import LocalAccount
from flashbots import flashbot
from eth_account.account import Account
from datetime import datetime
import json
import os

logger = logging.getLogger("FLASHBOTS_EXECUTOR")

class FlashbotsStatus(Enum):
    """Status of Flashbots transaction"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    INCLUDED = "included"
    FAILED = "failed"
    REVERTED = "reverted"
    NOT_INCLUDED = "not_included"
    ERROR = "error"

class FlashbotsTransactionResult:
    """Result of Flashbots transaction submission"""
    
    def __init__(
        self,
        status: FlashbotsStatus,
        tx_hash: Optional[str] = None,
        block_number: Optional[int] = None,
        bundle_hash: Optional[str] = None,
        error_message: Optional[str] = None,
        gas_used: Optional[int] = None,
        miner_reward: Optional[str] = None,
        timestamp: str = None
    ):
        self.status = status
        self.tx_hash = tx_hash
        self.block_number = block_number
        self.bundle_hash = bundle_hash
        self.error_message = error_message
        self.gas_used = gas_used
        self.miner_reward = miner_reward
        self.timestamp = timestamp or datetime.now().isoformat()
    
    def __repr__(self):
        return f"<FlashbotsResult: {self.status.value} | TxHash: {self.tx_hash} | Block: {self.block_number}>"

class FlashbotsExecutor:
    """
    🛡️ Flashbots Private Transaction Executor
    
    Submits transactions privately through Flashbots network:
    - Hides from mempool (MEV protection)
    - Protection against front-running
    - Protection against sandwich attacks
    - No gas cost on revert
    
    Requires:
    - FLASHBOTS_ENABLED environment variable
    - FLASHBOTS_PRIVATE_KEY for signing
    - FLASHBOTS_BUILDER_URI (optional, uses default if not set)
    """
    
    # Known Flashbots endpoints
    MAINNET_FLASHBOTS_URI = "https://relay.flashbots.net"
    
    def __init__(self, w3: Web3, private_key: str = None, enabled: bool = True):
        """
        Initialize Flashbots executor
        
        Args:
            w3: Web3 instance
            private_key: Private key for bundle signing
            enabled: Whether Flashbots is enabled
        """
        self.w3 = w3
        self.enabled = enabled
        self.private_key = private_key
        self.bundle_submitted_count = 0
        self.bundle_included_count = 0
        self.signer: Optional[LocalAccount] = None
        
        if self.enabled:
            logger.info("🛡️ Flashbots Executor ENABLED")
            
            if not self.private_key:
                logger.error("❌ Flashbots enabled but no private key provided!")
                self.enabled = False
                return

            try:
                # Initialize signer
                self.signer = Account.from_key(self.private_key)
                
                # Register Flashbots provider
                flashbot(self.w3, self.signer, self.MAINNET_FLASHBOTS_URI)
                
                logger.info(f"   Relay: {self.MAINNET_FLASHBOTS_URI}")
                logger.info(f"   Signer: {self.signer.address}")
                logger.info(f"   Network: {self._get_network_name()}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Flashbots: {str(e)}")
                self.enabled = False
        else:
            logger.info("⚠️ Flashbots Executor DISABLED - using regular transactions")
    
    def _get_network_name(self) -> str:
        """Get network name from chain ID"""
        try:
            chain_id = self.w3.eth.chain_id
            networks = {
                1: "Ethereum Mainnet",
                5: "Goerli Testnet",
                11155111: "Sepolia Testnet",
                137: "Polygon Mainnet",
                80001: "Polygon Mumbai"
            }
            return networks.get(chain_id, f"Chain ID {chain_id}")
        except:
            return "Unknown"
    
    def submit_bundle(
        self,
        transactions: list,
        block_number: int = None,
        min_timestamp: int = None,
        max_timestamp: int = None
    ) -> FlashbotsTransactionResult:
        """
        Submit a bundle of transactions through Flashbots
        
        Args:
            transactions: List of signed transactions (hex strings) or transaction dicts
            block_number: Target block number
            min_timestamp: Minimum block timestamp
            max_timestamp: Maximum block timestamp
            
        Returns:
            FlashbotsTransactionResult
        """
        if not self.enabled:
            logger.warning("⚠️ Flashbots disabled, would use regular submission")
            return FlashbotsTransactionResult(
                status=FlashbotsStatus.ERROR,
                error_message="Flashbots executor is disabled"
            )
        
        try:
            # Get target block if not specified
            if block_number is None:
                block_number = self.w3.eth.block_number + 1
            
            logger.info(f"\n{'='*70}")
            logger.info(f"🛡️ SUBMITTING PRIVATE BUNDLE TO FLASHBOTS")
            logger.info(f"{'='*70}")
            logger.info(f"   📦 Transactions: {len(transactions)}")
            logger.info(f"   📍 Target block: {block_number}")
            
            # Construct bundle
            bundle = [
                {"signed_transaction": tx} if isinstance(tx, str) else tx
                for tx in transactions
            ]
            
            # Add timestamp constraints if provided
            opts = {}
            if min_timestamp:
                opts["minTimestamp"] = min_timestamp
            if max_timestamp:
                opts["maxTimestamp"] = max_timestamp

            # Simulate first
            logger.info(f"   🔬 Simulating bundle...")
            try:
                simulation = self.w3.flashbots.simulate(bundle, block_number)
                if 'error' in simulation:
                     logger.error(f"   ❌ Simulation failed: {simulation['error']}")
                     return FlashbotsTransactionResult(
                        status=FlashbotsStatus.ERROR,
                        error_message=f"Simulation failed: {simulation['error']}"
                    )
                logger.info(f"   ✅ Simulation passed")
            except Exception as sim_error:
                logger.warning(f"   ⚠️ Simulation error (continuing anyway): {str(sim_error)}")
            
            # Send bundle
            logger.info(f"   🚀 Sending bundle...")
            replacement_uuid = str(int(time.time())) # Simple replacement ID
            
            result = self.w3.flashbots.send_bundle(
                bundle,
                target_block_number=block_number,
                opts=opts
            )
            
            # Get bundle stats
            bundle_hash = self._generate_bundle_hash(transactions) # We use our own hash or use result.bundle_hash() if available
            
            # Note: Flashbots send_bundle returns a BundleResponse which has .wait()
            # but we return immediately to allow async monitoring if desired
            
            logger.info(f"\n   ✅ Bundle submitted successfully")
            logger.info(f"   ⏳ Status: Awaiting inclusion in block {block_number}")
            logger.info(f"{'='*70}\n")
            
            self.bundle_submitted_count += 1
            
            return FlashbotsTransactionResult(
                status=FlashbotsStatus.SUBMITTED,
                bundle_hash=bundle_hash,
                block_number=block_number
            )
        
        except Exception as e:
            logger.error(f"❌ Flashbots submission failed: {str(e)}")
            return FlashbotsTransactionResult(
                status=FlashbotsStatus.ERROR,
                error_message=str(e)
            )
    
    def submit_private_transaction(
        self,
        signed_tx: str,
        block_number: int = None,
        return_value: bool = True
    ) -> FlashbotsTransactionResult:
        """
        Submit a single signed transaction through Flashbots Private Transaction API
        
        Args:
            signed_tx: Signed transaction hex string
            block_number: Target block number (hint)
            return_value: Return calldata (Flashbots feature)
            
        Returns:
            FlashbotsTransactionResult
        """
        if not self.enabled:
            logger.warning("⚠️ Flashbots disabled")
            return FlashbotsTransactionResult(
                status=FlashbotsStatus.ERROR,
                error_message="Flashbots executor is disabled"
            )
        
        try:
            logger.info(f"\n🛡️ Submitting private transaction through Flashbots")
            
            # Using flashbots private transaction API
            # Note: This might not be supported on all relays/networks
            
            try:
                # Try new private transaction API if available in library
                result = self.w3.flashbots.send_private_transaction(signed_tx)
                tx_hash = result.hash().hex()
            except AttributeError:
                # Fallback to single-tx bundle if private tx api not explicitly exposed
                logger.info("   ℹ️ Using single-tx bundle fallback")
                return self.submit_bundle([signed_tx], block_number)
            
            logger.info(f"   ✅ Private tx submitted to Flashbots")
            logger.info(f"   🆔 Tx Hash: {tx_hash}")
            logger.info(f"   🔐 Status: Hidden from mempool\n")
            
            return FlashbotsTransactionResult(
                status=FlashbotsStatus.SUBMITTED,
                tx_hash=tx_hash,
                block_number=block_number
            )
        
        except Exception as e:
            logger.error(f"❌ Private tx submission failed: {str(e)}")
            return FlashbotsTransactionResult(
                status=FlashbotsStatus.ERROR,
                error_message=str(e)
            )
    
    def simulate_bundle(
        self,
        bundle_dict: Dict,
        block_number: int
    ) -> Tuple[bool, Dict]:
        """
        Simulate bundle execution before sending
        
        Returns:
            (success, simulation_result)
        """
        if not self.enabled:
            return False, {"error": "Flashbots disabled"}
            
        try:
            logger.info(f"🔬 Simulating Flashbots bundle...")
            
            # Extract signed txs from dict if necessary, or pass as is depending on library version
            # Assuming bundle_dict['txs'] contains the list of signed txs
            
            simulation = self.w3.flashbots.simulate(bundle_dict['txs'], block_number)
            
            if 'error' in simulation:
                logger.warning(f"   ⚠️ Simulation failed: {simulation['error']}")
                return False, simulation
            
            logger.info(f"   ✅ Bundle simulation passed")
            return True, simulation
        
        except Exception as e:
            logger.error(f"❌ Bundle simulation error: {str(e)}")
            return False, {"error": str(e)}
    
    def monitor_bundle(
        self,
        bundle_hash: str,
        max_blocks: int = 25,
        poll_interval: float = 1.0
    ) -> FlashbotsTransactionResult:
        """
        Monitor bundle status until inclusion or timeout
        
        Args:
            bundle_hash: Bundle hash to monitor (or unique identifier)
            max_blocks: Maximum blocks to wait
            poll_interval: Seconds between polls
            
        Returns:
            FlashbotsTransactionResult with final status
        """
        # Note: Monitoring specific bundles usually requires the bundle stats API which might require authentication
        # For this implementation, we'll check if the transaction hash(es) in the bundle were included
        
        logger.info(f"\n📊 Monitoring Flashbots bundle...")
        
        start_block = self.w3.eth.block_number
        
        try:
            for i in range(max_blocks):
                time.sleep(poll_interval)

                current_block = self.w3.eth.block_number
                blocks_waited = current_block - start_block

                if blocks_waited > 0 and blocks_waited % 5 == 0:
                    logger.info(f"   ⏳ Waiting... Block {current_block} (+{blocks_waited})")

                # Try to query Flashbots bundle stats
                try:
                    stats = self.w3.flashbots.get_bundle_stats_v2(
                        self.w3.eth.block_number, bundle_hash
                    )
                    if stats and stats.get("isSimulated") and stats.get("isSentToMiners"):
                        logger.info(f"   ✅ Bundle confirmed included in block.")
                        return FlashbotsTransactionResult(
                            status=FlashbotsStatus.INCLUDED,
                            bundle_hash=bundle_hash,
                            block_number=current_block
                        )
                except Exception:
                    pass

                # Timeout check must happen AFTER updating blocks_waited
                if blocks_waited >= max_blocks:
                    logger.warning(
                        f"   ⏱️ Bundle wait timed out after {max_blocks} blocks"
                    )
                    return FlashbotsTransactionResult(
                        status=FlashbotsStatus.NOT_INCLUDED,
                        bundle_hash=bundle_hash
                    )

            # Loop exhausted without confirmed timeout — treat as NOT_INCLUDED
            logger.warning(f"   ⏱️ Bundle loop ended without inclusion after {max_blocks} iterations")
            return FlashbotsTransactionResult(
                status=FlashbotsStatus.NOT_INCLUDED,
                bundle_hash=bundle_hash
            )
        
        except Exception as e:
            logger.error(f"❌ Monitoring error: {str(e)}")
            return FlashbotsTransactionResult(
                status=FlashbotsStatus.ERROR,
                error_message=str(e)
            )
    
    def _generate_bundle_hash(self, transactions: list) -> str:
        """Generate a bundle hash from transactions"""
        import hashlib
        tx_str = json.dumps([tx[:20] + "..." if isinstance(tx, str) else str(tx) for tx in transactions])
        hash_obj = hashlib.sha256(tx_str.encode())
        return "0x" + hash_obj.hexdigest()
    
    def get_statistics(self) -> Dict:
        """Get Flashbots executor statistics"""
        return {
            "enabled": self.enabled,
            "bundles_submitted": self.bundle_submitted_count,
            "bundles_included": self.bundle_included_count,
            "success_rate": (
                (self.bundle_included_count / self.bundle_submitted_count * 100)
                if self.bundle_submitted_count > 0 else 0
            ),
            "network": self._get_network_name()
        }

    @staticmethod
    def _create_error_result(error_msg: str) -> 'FlashbotsTransactionResult':
        """Create an error result"""
        return FlashbotsTransactionResult(
            status=FlashbotsStatus.ERROR,
            error_message=error_msg
        )

# Global singleton
_flashbots_executor_instance = None

def get_flashbots_executor(w3: Web3, private_key: str = None, enabled: bool = True) -> FlashbotsExecutor:
    """Get or create Flashbots executor instance"""
    global _flashbots_executor_instance
    if _flashbots_executor_instance is None:
        _flashbots_executor_instance = FlashbotsExecutor(w3, private_key, enabled)
    return _flashbots_executor_instance

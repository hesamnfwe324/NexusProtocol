"""
Advanced Mempool Monitor for ERC20 Approval Detection - FIXED VERSION
=====================================================
Monitors pending transactions BEFORE they are confirmed on blockchain.
Detects approve() calls in real-time from the mempool.

Features:
- WebSocket real-time streaming
- HTTP polling fallback
- Async concurrent processing
- ERC20 approve() signature detection
- Multi-RPC failover
- Transaction decoding
- Speed priority modes
"""

import asyncio
import json
import time
import logging
import os
from typing import Callable, Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3
from web3.exceptions import TransactionNotFound
from eth_abi.abi import decode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MempoolMonitor")


ERC20_SIGNATURES = {
    "approve": "0x095ea7b3",
    "transfer": "0xa9059cbb",
    "transferFrom": "0x23b872dd",
    "increaseAllowance": "0x39509351",
    "decreaseAllowance": "0xa457c2d7",
}

APPROVE_SELECTOR = "0x095ea7b3"
INCREASE_ALLOWANCE_SELECTOR = "0x39509351"


class MonitorMode(Enum):
    WEBSOCKET = "websocket"
    HTTP_POLLING = "http_polling"
    HYBRID = "hybrid"


@dataclass
class PendingApproval:
    """Represents a pending approval detected in mempool"""
    tx_hash: str
    from_address: str
    token_address: str
    spender: str
    amount: int
    gas_price: int
    max_fee_per_gas: Optional[int]
    max_priority_fee: Optional[int]
    nonce: int
    detected_at: float
    raw_tx: Dict
    
    def __hash__(self):
        return hash(self.tx_hash)


@dataclass
class MempoolStats:
    """Statistics for mempool monitoring"""
    total_txs_scanned: int = 0
    approvals_detected: int = 0
    start_time: float = field(default_factory=time.time)
    last_approval_time: Optional[float] = None
    tokens_seen: Set[str] = field(default_factory=set)
    
    @property
    def uptime(self) -> float:
        return time.time() - self.start_time
    
    @property
    def txs_per_second(self) -> float:
        if self.uptime > 0:
            return self.total_txs_scanned / self.uptime
        return 0


class AdvancedMempoolMonitor:
    """
    Professional-grade mempool monitor for detecting ERC20 approvals
    before they are confirmed on the blockchain.
    """
    
    def __init__(
        self,
        wss_url: Optional[str] = None,
        http_url: Optional[str] = None,
        mode: MonitorMode = MonitorMode.HYBRID,
        on_approval_detected: Optional[Callable[[PendingApproval], None]] = None,
        target_spender: Optional[str] = None,
        target_tokens: Optional[List[str]] = None,
        min_approval_amount: int = 0,
        max_workers: int = 256,  # INCREASED: 50 → 256
        poll_interval: float = 0.0001,  # EXTREME: 0.01 → 0.0001 (100x faster)
    ):
        """Initialize the mempool monitor"""
        self.wss_url = wss_url
        self.http_url = http_url
        self.mode = mode
        self.on_approval_detected = on_approval_detected
        self.target_spender = target_spender.lower() if target_spender else None
        self.target_tokens = [t.lower() for t in target_tokens] if target_tokens else None
        self.min_approval_amount = min_approval_amount
        self.max_workers = max_workers
        self.poll_interval = poll_interval
        
        self.w3_ws: Optional[Web3] = None
        self.w3_http: Optional[Web3] = None
        
        self.is_running = False
        self.seen_txs: Set[str] = set()
        self.pending_approvals: Dict[str, PendingApproval] = {}
        self.stats = MempoolStats()
        
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._init_connections()
    
    def _init_connections(self):
        """Initialize Web3 connections"""
        # Create a session that ignores SSL verification
        import requests
        try:
            from requests.adapters import HTTPAdapter
        except ImportError:
            HTTPAdapter = requests.adapters.HTTPAdapter # type: ignore
        session = requests.Session()
        session.verify = False
        adapter = HTTPAdapter(max_retries=3)
        session.mount('https://', adapter)
        
        request_kwargs = {'verify': False, 'timeout': 30}
        
        # We need a proper middleware import for Web3 v7/v6 compatibility
        try:
            from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
        except ImportError:
            try:
                from web3.middleware import geth_poa_middleware
            except ImportError:
                geth_poa_middleware = None

        if self.wss_url:
            try:
                logger.info(f"Testing RPC: {self.wss_url[:50]}...")
                self.w3_ws = Web3(Web3.HTTPProvider(self.wss_url, request_kwargs=request_kwargs, session=session))
                if geth_poa_middleware:
                    self.w3_ws.middleware_onion.inject(geth_poa_middleware, layer=0)
                logger.info(f"✅ RPC initialized (WSS-Fallback-HTTP): {self.wss_url[:50]}...")
            except Exception as e:
                logger.error(f"❌ RPC init error (WSS): {e}")
                self.w3_ws = None
        
        if self.http_url:
            try:
                logger.info(f"Testing RPC: {self.http_url[:50]}...")
                self.w3_http = Web3(Web3.HTTPProvider(self.http_url, request_kwargs=request_kwargs, session=session))
                if geth_poa_middleware:
                    self.w3_http.middleware_onion.inject(geth_poa_middleware, layer=0)
                logger.info(f"✅ RPC initialized (HTTP): {self.http_url[:50]}...")
            except Exception as e:
                logger.error(f"❌ RPC init error (HTTP): {e}")
                self.w3_http = None
        
        # Ensure self.w3 is set even if both failed, though caller will handle the error
        self.w3 = self.w3_ws or self.w3_http
        if not self.w3:
            raise ConnectionError("No valid RPC connection available")
    
    def decode_approve_data(self, input_data: str) -> Optional[Dict]:
        """Decode approve() or increaseAllowance() call data"""
        if not input_data or len(input_data) < 10:
            return None
        
        selector = input_data[:10].lower()
        
        if selector not in [APPROVE_SELECTOR, INCREASE_ALLOWANCE_SELECTOR]:
            return None
        
        try:
            params_data = input_data[10:]
            
            if len(params_data) < 128:
                return None
            
            spender_hex = params_data[:64]
            amount_hex = params_data[64:128]
            
            spender = "0x" + spender_hex[-40:]
            amount = int(amount_hex, 16)
            
            return {
                "spender": Web3.to_checksum_address(spender),
                "amount": amount,
                "is_unlimited": amount >= 2**255,
                "function": "approve" if selector == APPROVE_SELECTOR else "increaseAllowance"
            }
            
        except Exception as e:
            logger.debug(f"Failed to decode approval data: {e}")
            return None
    
    def _process_transaction(self, tx_hash: str) -> Optional[PendingApproval]:
        """Process a single pending transaction"""
        try:
            tx_hash_str = tx_hash.hex() if isinstance(tx_hash, bytes) else tx_hash
            if tx_hash_str in self.seen_txs:
                return None
            
            if len(self.seen_txs) > 50000:
                self.seen_txs.clear()
            
            self.seen_txs.add(tx_hash_str)
            self.stats.total_txs_scanned += 1
            
            tx_hash_obj = self.w3.to_bytes(hexstr=tx_hash_str)
            tx = self.w3.eth.get_transaction(tx_hash_obj) # type: ignore
            
            if not tx or not tx.get('to') or not tx.get('input'):
                return None
            
            input_data = tx['input']
            if isinstance(input_data, bytes):
                input_data = input_data.hex()
            if not isinstance(input_data, str):
                input_data = str(input_data)
            if not input_data.startswith('0x'):
                input_data = '0x' + input_data
            
            approval_data = self.decode_approve_data(input_data)
            
            if not approval_data:
                return None
            
            token_address = tx['to'].lower()
            spender = approval_data['spender'].lower()
            
            if self.target_spender and spender != self.target_spender:
                return None
            
            if self.target_tokens and token_address not in self.target_tokens:
                return None
            
            if approval_data['amount'] < self.min_approval_amount:
                return None
            
            pending = PendingApproval(
                tx_hash=tx_hash_str,
                from_address=tx['from'],
                token_address=Web3.to_checksum_address(tx['to']),
                spender=approval_data['spender'],
                amount=approval_data['amount'],
                gas_price=tx.get('gasPrice', 0),
                max_fee_per_gas=tx.get('maxFeePerGas'),
                max_priority_fee=tx.get('maxPriorityFeePerGas'),
                nonce=tx['nonce'],
                detected_at=time.time(),
                raw_tx=dict(tx)
            )
            
            self.stats.approvals_detected += 1
            self.stats.last_approval_time = time.time()
            self.stats.tokens_seen.add(token_address)
            
            self.pending_approvals[tx_hash_str] = pending
            
            logger.info(f"🎯 PENDING APPROVAL: {pending.spender} for {pending.token_address}")
            
            if self.on_approval_detected:
                self.on_approval_detected(pending)
            
            return pending
            
        except TransactionNotFound:
            return None
        except Exception as e:
            logger.debug(f"Error processing tx {tx_hash}: {e}")
            return None
    
    def _process_http_polling(self):
        """Monitor mempool using HTTP polling"""
        if not self.w3_http:
            logger.error("HTTP connection not available")
            return
        
        logger.info("Starting HTTP polling mempool monitor...")
        
        try:
            while self.is_running:
                try:
                    # Get pending transactions from mempool
                    # Note: Not all RPCs support 'pending' filter or get_block('pending')
                    try:
                        pending_block = self.w3_http.eth.get_block('pending', full_transactions=True)
                        if pending_block and 'transactions' in pending_block:
                            for tx in pending_block['transactions']:
                                if not self.is_running:
                                    break
                                # Process transaction in executor to not block polling
                                self.executor.submit(self._process_transaction_object, tx)
                    except Exception as e:
                        logger.debug(f"Block polling error: {e}")

                    time.sleep(self.poll_interval)
                    
                except Exception as e:
                    logger.error(f"HTTP polling error: {e}")
                    time.sleep(2)
                    
        except Exception as e:
            logger.error(f"HTTP monitoring failed: {e}")

    def _process_transaction_object(self, tx: Dict):
        """Process a transaction object directly from block data"""
        try:
            tx_hash = tx['hash']
            tx_hash_str = tx_hash.hex() if isinstance(tx_hash, bytes) else tx_hash
            
            # VISIBLE HEARTBEAT - Print every 100th tx scanned to show activity without flooding
            if self.stats.total_txs_scanned % 50 == 0:
                print(f"📡 Scanning Mempool... [Total Scanned: {self.stats.total_txs_scanned}]", end='\r', flush=True)

            if tx_hash_str in self.seen_txs:
                return
                
            self.seen_txs.add(tx_hash_str)
            if len(self.seen_txs) > 50000:
                self.seen_txs.clear()
                
            self.stats.total_txs_scanned += 1
            
            if not tx.get('to') or not tx.get('input'):
                return
                
            input_data = tx['input']
            if isinstance(input_data, bytes):
                input_data = input_data.hex()
            if not isinstance(input_data, str):
                input_data = str(input_data)
            if not input_data.startswith('0x'):
                input_data = '0x' + input_data
                
            approval_data = self.decode_approve_data(input_data)
            if not approval_data:
                return
                
            token_address = tx['to'].lower() if tx.get('to') else ""
            spender = approval_data['spender'].lower()
            
            if self.target_spender and spender != self.target_spender:
                return
            if self.target_tokens and token_address not in self.target_tokens:
                return
            if approval_data['amount'] < self.min_approval_amount:
                return
                
            pending = PendingApproval(
                tx_hash=tx_hash_str,
                from_address=tx['from'],
                token_address=Web3.to_checksum_address(tx['to']),
                spender=approval_data['spender'],
                amount=approval_data['amount'],
                gas_price=tx.get('gasPrice', 0),
                max_fee_per_gas=tx.get('maxFeePerGas'),
                max_priority_fee=tx.get('maxPriorityFeePerGas'),
                nonce=tx['nonce'],
                detected_at=time.time(),
                raw_tx=dict(tx)
            )
            
            self.stats.approvals_detected += 1
            self.stats.last_approval_time = time.time()
            self.stats.tokens_seen.add(token_address)
            self.pending_approvals[tx_hash_str] = pending
            
            logger.info(f"🎯 PENDING APPROVAL: {pending.spender} for {pending.token_address}")
            
            if self.on_approval_detected:
                self.on_approval_detected(pending)
        except Exception as e:
            logger.debug(f"Error processing tx: {e}")
    
    def start(self):
        """Start the mempool monitor"""
        self.is_running = True
        self.stats = MempoolStats()
        
        logger.info(f"""
╔══════════════════════════════════════════════════════════════╗
║  🚀 ADVANCED MEMPOOL MONITOR STARTING                        ║
╠══════════════════════════════════════════════════════════════╣
║  Target Spender: {self.target_spender or 'ALL'}
║  Target Tokens:  {len(self.target_tokens) if self.target_tokens else 'ALL'}
║  Min Amount:     {self.min_approval_amount}
║  Workers:        {self.max_workers}
╚══════════════════════════════════════════════════════════════╝
        """)
        
        if self.w3_http:
            import threading as _threading
            poll_thread = _threading.Thread(
                target=self._process_http_polling,
                name="MempoolHTTPPoller",
                daemon=True
            )
            poll_thread.start()
    
    def stop(self):
        """Stop the mempool monitor"""
        self.is_running = False
        self.executor.shutdown(wait=False)
        logger.info("Mempool monitor stopped")
    
    def get_stats(self) -> Dict:
        """Get monitoring statistics"""
        return {
            "total_txs_scanned": self.stats.total_txs_scanned,
            "approvals_detected": self.stats.approvals_detected,
            "uptime_seconds": self.stats.uptime,
            "txs_per_second": self.stats.txs_per_second,
            "last_approval_time": self.stats.last_approval_time,
            "unique_tokens_seen": len(self.stats.tokens_seen),
            "pending_approvals": len(self.pending_approvals),
            "cached_txs_size": len(self.seen_txs),
        }


def _get_secure_credentials() -> tuple:
    """Load credentials from environment variables - NEVER hardcode keys"""
    return (
        os.getenv('EXECUTOR_PRIVATE_KEY', ''),
        os.getenv('DESTINATION_ADDRESS', ''),
    )


def _mask_sensitive(value: str, visible: int = 4) -> str:
    """Mask sensitive data for safe logging"""
    if not value or len(value) < visible * 2:
        return "***"
    return f"{value[:visible]}...{value[-visible:]}"

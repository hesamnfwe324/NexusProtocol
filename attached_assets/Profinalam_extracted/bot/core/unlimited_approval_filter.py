"""
Unlimited Approval Filter & Monitor
Detects, tracks, and monitors unlimited token approvals
Alerts when status changes (e.g., from unlimited to limited)
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from web3 import Web3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('unlimited_approvals.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class UnlimitedApprovalStatus(Enum):
    """Status of unlimited approval tracking"""
    ACTIVE = "active"              # Still unlimited
    CHANGED = "changed"            # No longer unlimited
    REVOKED = "revoked"            # Set to zero
    MONITORED = "monitored"        # Being watched
    ALERT_SENT = "alert_sent"      # Alert was sent


@dataclass
class UnlimitedApproval:
    """Represents a detected unlimited approval"""
    id: int
    owner: str
    spender: str
    token_address: str
    token_symbol: str
    initial_amount: str
    current_amount: str
    decimals: int
    detected_at: str
    last_checked: str
    status: str
    alert_count: int
    notes: str

    def to_dict(self) -> Dict:
        return asdict(self)


class UnlimitedApprovalFilter:
    """Detects and monitors unlimited token approvals"""
    
    # MAX_UINT256 = 2^256 - 1
    MAX_UINT256 = 115792089237316195423570985008687907853269984665640564039457584007913129639935
    UNLIMITED_THRESHOLD = MAX_UINT256 * 0.9  # 90% of max = likely unlimited
    
    DB_PATH = "unlimited_approvals.db"
    
    def __init__(self, w3: Web3, on_status_change: Optional[Callable] = None):
        """
        Initialize the unlimited approval filter
        
        Args:
            w3: Web3 instance for blockchain queries
            on_status_change: Callback when approval status changes
        """
        self.w3 = w3
        self.on_status_change = on_status_change
        self._init_db()
        logger.info("✅ Unlimited Approval Filter initialized")
    
    def _init_db(self):
        """Initialize SQLite database for tracking unlimited approvals"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS unlimited_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL,
                spender TEXT NOT NULL,
                token_address TEXT NOT NULL,
                token_symbol TEXT NOT NULL,
                initial_amount TEXT NOT NULL,
                current_amount TEXT NOT NULL,
                decimals INTEGER NOT NULL,
                detected_at TEXT NOT NULL,
                last_checked TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                alert_count INTEGER DEFAULT 0,
                notes TEXT,
                UNIQUE(owner, spender, token_address)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS approval_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unlimited_approval_id INTEGER NOT NULL,
                old_amount TEXT,
                new_amount TEXT,
                old_status TEXT,
                new_status TEXT,
                changed_at TEXT NOT NULL,
                FOREIGN KEY(unlimited_approval_id) REFERENCES unlimited_approvals(id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def is_unlimited(self, amount: int) -> bool:
        """
        Check if an approval amount is unlimited
        
        Args:
            amount: The approval amount in smallest unit
            
        Returns:
            True if amount represents unlimited approval
        """
        return amount >= self.UNLIMITED_THRESHOLD
    
    def detect_approval(self, owner: str, spender: str, token_address: str, 
                       amount: int, token_symbol: str = "UNKNOWN", 
                       decimals: int = 18) -> Optional[UnlimitedApproval]:
        """
        Detect if an approval is unlimited and track it
        
        Args:
            owner: Token owner address
            spender: Spender address
            token_address: Token contract address
            amount: Approval amount
            token_symbol: Token symbol for logging
            decimals: Token decimals
            
        Returns:
            UnlimitedApproval object if unlimited, None otherwise
        """
        if not self.is_unlimited(amount):
            return None
        
        # Check if already tracked
        existing = self._get_approval(owner, spender, token_address)
        
        if existing:
            # Update last checked and current amount
            self._update_approval_check(
                existing.id, 
                str(amount),
                UnlimitedApprovalStatus.ACTIVE.value
            )
            logger.info(f"🔄 Updated unlimited approval: {owner[:8]} → {spender[:8]} ({token_symbol})")
            return existing
        else:
            # New unlimited approval detected
            approval = self._insert_approval(
                owner, spender, token_address, token_symbol,
                str(amount), str(amount), decimals
            )
            logger.warning(f"🚨 NEW UNLIMITED APPROVAL DETECTED!")
            logger.warning(f"   Owner: {owner}")
            logger.warning(f"   Spender: {spender}")
            logger.warning(f"   Token: {token_symbol} ({token_address[:8]}...)")
            logger.warning(f"   Amount: UNLIMITED (2^256-1)")
            return approval
    
    def monitor_approval(self, approval: UnlimitedApproval, 
                        token_abi: List) -> Optional[Dict]:
        """
        Monitor an unlimited approval for status changes
        
        Args:
            approval: UnlimitedApproval to monitor
            token_abi: ERC20 contract ABI
            
        Returns:
            Change info if status changed, None otherwise
        """
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(approval.token_address),
                abi=token_abi
            )
            
            # Get current allowance
            current_amount = contract.functions.allowance(
                Web3.to_checksum_address(approval.owner),
                Web3.to_checksum_address(approval.spender)
            ).call()
            
            current_amount_str = str(current_amount)
            
            # Check if status changed
            if not self.is_unlimited(current_amount):
                # Status changed - was unlimited, now isn't
                change_info = {
                    "approval_id": approval.id,
                    "owner": approval.owner,
                    "spender": approval.spender,
                    "token": approval.token_symbol,
                    "old_status": UnlimitedApprovalStatus.ACTIVE.value,
                    "new_status": UnlimitedApprovalStatus.CHANGED.value if current_amount > 0 else UnlimitedApprovalStatus.REVOKED.value,
                    "previous_amount": approval.current_amount,
                    "current_amount": current_amount_str,
                    "changed_at": datetime.now().isoformat()
                }
                
                # Update status
                self._update_approval_status(
                    approval.id,
                    change_info["new_status"],
                    current_amount_str
                )
                
                # Record history
                self._record_change(
                    approval.id,
                    approval.current_amount,
                    current_amount_str,
                    UnlimitedApprovalStatus.ACTIVE.value,
                    change_info["new_status"]
                )
                
                # Trigger callback
                if self.on_status_change:
                    self.on_status_change(change_info)
                
                logger.warning(f"⚠️ UNLIMITED APPROVAL STATUS CHANGED!")
                logger.warning(f"   Owner: {approval.owner}")
                logger.warning(f"   Spender: {approval.spender}")
                logger.warning(f"   Token: {approval.token_symbol}")
                logger.warning(f"   Previous: UNLIMITED")
                logger.warning(f"   Current: {current_amount}")
                
                return change_info
            else:
                # Still unlimited, just update last checked
                self._update_approval_check(
                    approval.id,
                    current_amount_str,
                    UnlimitedApprovalStatus.ACTIVE.value
                )
            
            return None
        
        except Exception as e:
            logger.error(f"Error monitoring approval {approval.id}: {str(e)}")
            return None
    
    def get_active_approvals(self) -> List[UnlimitedApproval]:
        """Get all active unlimited approvals"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, owner, spender, token_address, token_symbol, 
                   initial_amount, current_amount, decimals, 
                   detected_at, last_checked, status, alert_count, notes
            FROM unlimited_approvals
            WHERE status = ?
            ORDER BY detected_at DESC
        ''', (UnlimitedApprovalStatus.ACTIVE.value,))
        
        rows = cursor.fetchall()
        conn.close()
        
        approvals = []
        for row in rows:
            approvals.append(UnlimitedApproval(*row))
        
        return approvals
    
    def get_changed_approvals(self) -> List[UnlimitedApproval]:
        """Get all approvals that have changed status"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, owner, spender, token_address, token_symbol, 
                   initial_amount, current_amount, decimals, 
                   detected_at, last_checked, status, alert_count, notes
            FROM unlimited_approvals
            WHERE status IN (?, ?)
            ORDER BY last_checked DESC
        ''', (UnlimitedApprovalStatus.CHANGED.value, UnlimitedApprovalStatus.REVOKED.value))
        
        rows = cursor.fetchall()
        conn.close()
        
        approvals = []
        for row in rows:
            approvals.append(UnlimitedApproval(*row))
        
        return approvals
    
    def _get_approval(self, owner: str, spender: str, token_address: str) -> Optional[UnlimitedApproval]:
        """Get an approval from database"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, owner, spender, token_address, token_symbol, 
                   initial_amount, current_amount, decimals, 
                   detected_at, last_checked, status, alert_count, notes
            FROM unlimited_approvals
            WHERE owner = ? AND spender = ? AND token_address = ?
        ''', (owner, spender, token_address))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return UnlimitedApproval(*row)
        return None
    
    def _insert_approval(self, owner: str, spender: str, token_address: str,
                        token_symbol: str, initial_amount: str, current_amount: str,
                        decimals: int) -> UnlimitedApproval:
        """Insert new unlimited approval"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO unlimited_approvals
            (owner, spender, token_address, token_symbol, initial_amount, 
             current_amount, decimals, detected_at, last_checked, status, alert_count, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (owner, spender, token_address, token_symbol, initial_amount,
              current_amount, decimals, now, now, UnlimitedApprovalStatus.ACTIVE.value, 0, ""))
        
        conn.commit()
        approval_id = cursor.lastrowid
        conn.close()
        
        return UnlimitedApproval(
            id=approval_id,
            owner=owner,
            spender=spender,
            token_address=token_address,
            token_symbol=token_symbol,
            initial_amount=initial_amount,
            current_amount=current_amount,
            decimals=decimals,
            detected_at=now,
            last_checked=now,
            status=UnlimitedApprovalStatus.ACTIVE.value,
            alert_count=0,
            notes=""
        )
    
    def _update_approval_check(self, approval_id: int, current_amount: str, status: str):
        """Update approval last check time"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE unlimited_approvals
            SET last_checked = ?, current_amount = ?, status = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), current_amount, status, approval_id))
        
        conn.commit()
        conn.close()
    
    def _update_approval_status(self, approval_id: int, status: str, current_amount: str):
        """Update approval status"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE unlimited_approvals
            SET status = ?, current_amount = ?, last_checked = ?, alert_count = alert_count + 1
            WHERE id = ?
        ''', (status, current_amount, datetime.now().isoformat(), approval_id))
        
        conn.commit()
        conn.close()
    
    def _record_change(self, approval_id: int, old_amount: str, new_amount: str,
                       old_status: str, new_status: str):
        """Record approval status change in history"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO approval_history
            (unlimited_approval_id, old_amount, new_amount, old_status, new_status, changed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (approval_id, old_amount, new_amount, old_status, new_status, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def export_to_json(self, filename: str = "unlimited_approvals.json"):
        """Export all unlimited approvals to JSON"""
        active = self.get_active_approvals()
        changed = self.get_changed_approvals()
        
        data = {
            "exported_at": datetime.now().isoformat(),
            "active_approvals": [a.to_dict() for a in active],
            "changed_approvals": [a.to_dict() for a in changed],
            "total_active": len(active),
            "total_changed": len(changed)
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"✅ Exported {len(active) + len(changed)} approvals to {filename}")

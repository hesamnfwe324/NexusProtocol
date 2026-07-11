"""
🔐 SECURE CONFIGURATION MODULE
Manages sensitive data (private keys, API keys) securely using environment variables.
NEVER stores or logs sensitive information in plain text.
"""

import os
import logging
import hashlib
from typing import Optional, Dict
from functools import lru_cache

logger = logging.getLogger(__name__)


class SecureKeyManager:
    """
    Secure management of private keys and sensitive data.
    All keys are loaded from environment variables only.
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if SecureKeyManager._initialized:
            return
        SecureKeyManager._initialized = True
        self._validate_environment()
    
    def _validate_environment(self):
        """Check if required environment variables are set"""
        required_vars = ['EXECUTOR_PRIVATE_KEY', 'DESTINATION_ADDRESS']
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            logger.warning(
                f"Missing environment variables: {missing}. "
                "Set them before running the bot."
            )
    
    @staticmethod
    def get_private_key() -> Optional[str]:
        """
        Get private key from environment variable.
        Returns None if not set.
        NEVER logs or prints the actual key.
        Returns key exactly as provided - Web3 handles 0x prefix.
        """
        key = os.getenv('EXECUTOR_PRIVATE_KEY')
        if key:
            clean_key = key[2:] if key.startswith('0x') else key
            if len(clean_key) != 64:
                logger.error("Invalid private key format (expected 64 hex chars)")
                return None
        return key
    
    @staticmethod
    def get_destination_address() -> Optional[str]:
        """Get destination address from environment variable"""
        return os.getenv('DESTINATION_ADDRESS')
    
    @staticmethod
    def get_rpc_url(network: str = 'ethereum') -> Optional[str]:
        """Get RPC URL from environment variable"""
        env_key = f'{network.upper()}_RPC_URL'
        return os.getenv(env_key) or os.getenv('RPC_URL')
    
    @staticmethod
    def get_wss_url() -> Optional[str]:
        """Get WebSocket URL from environment variable"""
        return os.getenv('WSS_URL')
    
    @staticmethod
    def get_api_key(provider: str) -> Optional[str]:
        """Get API key for specific provider"""
        env_key = f'{provider.upper()}_API_KEY'
        return os.getenv(env_key)
    
    @staticmethod
    def mask_key(key: str, visible_chars: int = 4) -> str:
        """
        Mask a key for safe logging.
        Shows only first and last few characters.
        """
        if not key or len(key) < visible_chars * 2:
            return "***"
        return f"{key[:visible_chars]}...{key[-visible_chars:]}"
    
    @staticmethod
    def mask_address(address: str) -> str:
        """Mask an address for safe logging"""
        if not address or len(address) < 10:
            return "***"
        return f"{address[:6]}...{address[-4:]}"
    
    @staticmethod
    def get_key_hash(key: str) -> str:
        """
        Get a hash of the key for identification purposes.
        Useful for logging without exposing the actual key.
        """
        if not key:
            return "no-key"
        return hashlib.sha256(key.encode()).hexdigest()[:12]
    
    def is_configured(self) -> bool:
        """Check if all required configuration is present"""
        return bool(
            self.get_private_key() and 
            self.get_destination_address()
        )
    
    def get_secure_config(self) -> Dict:
        """
        Get configuration dict with sensitive data loaded from env vars.
        Safe to use - no sensitive data is exposed.
        """
        private_key = self.get_private_key()
        destination = self.get_destination_address()
        
        return {
            "has_private_key": bool(private_key),
            "has_destination": bool(destination),
            "destination_masked": self.mask_address(destination) if destination else None,
            "key_hash": self.get_key_hash(private_key) if private_key else None,
            "rpc_configured": bool(self.get_rpc_url()),
            "wss_configured": bool(self.get_wss_url()),
        }
    
    def get_executor_config(self) -> Dict:
        """
        Get executor configuration with private key from environment.
        Returns config dict suitable for TriggerExecutor.
        """
        return {
            "destination_address": self.get_destination_address() or "",
            "private_key": self.get_private_key() or "",
            "min_amount_usd": float(os.getenv('MIN_AMOUNT_USD', '0.01')),
            "max_gas_price_gwei": int(os.getenv('MAX_GAS_GWEI', '200')),
            "gas_limit": int(os.getenv('GAS_LIMIT', '150000')),
            "retry_count": int(os.getenv('RETRY_COUNT', '5')),
            "speed_mode": os.getenv('SPEED_MODE', 'fast'),
            "use_eip1559": os.getenv('USE_EIP1559', 'true').lower() == 'true',
            "priority_fee_gwei": int(os.getenv('PRIORITY_FEE_GWEI', '2')),
        }


def get_secure_manager() -> SecureKeyManager:
    """Get singleton instance of SecureKeyManager"""
    return SecureKeyManager()


def validate_private_key(key: str) -> bool:
    """Validate private key format without logging it"""
    if not key:
        return False
    if key.startswith('0x'):
        key = key[2:]
    if len(key) != 64:
        return False
    try:
        int(key, 16)
        return True
    except ValueError:
        return False


def safe_log_transaction(tx_hash: str, from_addr: str, to_addr: str, amount: float, symbol: str):
    """Log transaction details safely with masked addresses"""
    manager = get_secure_manager()
    logger.info(
        f"TX: {tx_hash} | "
        f"From: {manager.mask_address(from_addr)} | "
        f"To: {manager.mask_address(to_addr)} | "
        f"Amount: {amount} {symbol}"
    )

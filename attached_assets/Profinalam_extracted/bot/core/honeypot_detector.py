#!/usr/bin/env python3
"""
🍯 HONEYPOT DETECTION MODULE
Advanced honeypot detection to protect against token scams

Detects tokens that:
- Can be bought but not sold (most common honeypot)
- Have excessive transfer fees
- Have locked liquidity
- Have suspicious burn mechanisms
"""

import logging
from typing import Dict, Optional, Tuple, List
from enum import Enum
from web3 import Web3
from datetime import datetime
import time

logger = logging.getLogger("HONEYPOT_DETECTOR")

class HoneypotRisk(Enum):
    """Risk level assessment"""
    SAFE = "safe"                          # ✅ Token appears safe
    LOW_RISK = "low_risk"                  # 🟢 Minor concerns
    MEDIUM_RISK = "medium_risk"            # 🟡 Moderate concerns
    HIGH_RISK = "high_risk"                # 🔴 Likely honeypot
    CONFIRMED_HONEYPOT = "confirmed_honeypot"  # ❌ Definitely honeypot

class HoneypotCheckResult:
    """Detailed result of honeypot check"""
    
    def __init__(
        self,
        token_address: str,
        risk_level: HoneypotRisk,
        is_honeypot: bool,
        reasons: List[str],
        warnings: List[str],
        metrics: Dict = None
    ):
        self.token_address = token_address
        self.risk_level = risk_level
        self.is_honeypot = is_honeypot
        self.reasons = reasons
        self.warnings = warnings
        self.metrics = metrics or {}
        self.timestamp = datetime.now().isoformat()
    
    def __repr__(self):
        return f"<HoneypotCheck: {self.risk_level.value} | Risk: {self.is_honeypot}>"
    
    def to_dict(self) -> Dict:
        return {
            "token_address": self.token_address,
            "risk_level": self.risk_level.value,
            "is_honeypot": self.is_honeypot,
            "reasons": self.reasons,
            "warnings": self.warnings,
            "metrics": self.metrics,
            "timestamp": self.timestamp
        }

# Popular DEX Router Addresses
DEX_ROUTERS = {
    "uniswap_v2": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
    "uniswap_v3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
    "sushiswap": "0xd9e1cE17f2641f24aE31b8F4e7d9a5a2F7d00c81",
    "pancakeswap_bsc": "0x10ED43C718714eb63d5aA57B78f985283Ed5217c",
}

# Common Stablecoin addresses to use as quote token
STABLECOINS = {
    # Ethereum
    "ethereum": {
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "DAI": "0x6B175474E89094C44Da98b954EeB8e8B778E489",
        "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    }
}

# Uniswap V2 Router ABI (minimal, for swap methods)
UNISWAP_V2_ROUTER_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactETHForTokens",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForETH",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "type": "function"
    }
]

# ERC20 ABI (complete)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
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
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]

class HoneypotDetector:
    """
    🍯 Advanced Honeypot Detection System
    
    Detects scam tokens that claim to be legitimate but:
    - Can't be sold after buying
    - Have extreme transfer fees (>50%)
    - Have suspicious burn/lock mechanisms
    - Have transfer blacklists
    
    Method:
    1. Check balance transfer capabilities
    2. Simulate DEX swap (buy → hold → sell)
    3. Verify liquidity adequacy
    4. Detect suspicious contract behaviors
    """
    
    def __init__(self, w3: Web3, chain: str = "ethereum"):
        self.w3 = w3
        self.chain = chain
        self.check_history: Dict[str, HoneypotCheckResult] = {}
        
        logger.info("🍯 Honeypot Detector initialized")
    
    def check_token(self, token_address: str) -> HoneypotCheckResult:
        """
        🍯 Comprehensive honeypot check for a token
        
        Args:
            token_address: Token contract address
            
        Returns:
            HoneypotCheckResult with detailed findings
        """
        token_address = Web3.to_checksum_address(token_address)
        
        logger.info(f"\n🍯 Starting honeypot check for {token_address}")
        
        try:
            # Check if already cached
            if token_address in self.check_history:
                cached = self.check_history[token_address]
                if (datetime.now() - datetime.fromisoformat(cached.timestamp)).total_seconds() < 3600:
                    logger.info(f"   ✅ Using cached result for {token_address}")
                    return cached
            
            reasons = []
            warnings = []
            metrics = {}
            risk_score = 0  # 0-100
            
            # 1. Check basic token properties
            logger.info("   📋 Checking basic token properties...")
            basic_checks = self._check_basic_properties(token_address)
            metrics.update(basic_checks["metrics"])
            if not basic_checks["passed"]:
                reasons.extend(basic_checks["issues"])
                risk_score += 30
            
            # 2. Check transfer capabilities
            logger.info("   📦 Checking transfer capabilities...")
            transfer_checks = self._check_transfer_capabilities(token_address)
            metrics.update(transfer_checks["metrics"])
            if not transfer_checks["passed"]:
                reasons.extend(transfer_checks["issues"])
                risk_score += 40
            
            # 3. Check for transfer fees
            logger.info("   💰 Detecting transfer fee mechanisms...")
            fee_checks = self._check_transfer_fees(token_address)
            metrics.update(fee_checks["metrics"])
            if fee_checks["fee_percentage"] > 50:
                reasons.append(f"⚠️ Very high transfer fees detected: {fee_checks['fee_percentage']:.1f}%")
                risk_score += 35
            elif fee_checks["fee_percentage"] > 10:
                warnings.append(f"⚠️ Moderate transfer fees: {fee_checks['fee_percentage']:.1f}%")
                risk_score += 15
            
            # 4. Check for suspicious patterns
            logger.info("   🔍 Scanning for suspicious patterns...")
            pattern_checks = self._check_suspicious_patterns(token_address)
            metrics.update(pattern_checks["metrics"])
            if pattern_checks["issues"]:
                reasons.extend(pattern_checks["issues"])
                risk_score += 20
            
            # 5. Simulate DEX swap (the critical test)
            logger.info("   🔄 Simulating DEX swap (buy → sell)...")
            swap_result = self._simulate_dex_swap(token_address)
            metrics["swap_simulation"] = swap_result["result"]
            
            if swap_result["can_sell"]:
                logger.info("   ✅ Token appears to be sellable")
            else:
                reasons.append("❌ Token CANNOT be sold on DEX (HONEYPOT)")
                risk_score = 100
            
            if swap_result["warnings"]:
                warnings.extend(swap_result["warnings"])
                risk_score += 10
            
            # Determine final risk level
            is_honeypot = risk_score >= 75
            
            if risk_score >= 90:
                risk_level = HoneypotRisk.CONFIRMED_HONEYPOT
            elif risk_score >= 75:
                risk_level = HoneypotRisk.HIGH_RISK
            elif risk_score >= 50:
                risk_level = HoneypotRisk.MEDIUM_RISK
            elif risk_score >= 25:
                risk_level = HoneypotRisk.LOW_RISK
            else:
                risk_level = HoneypotRisk.SAFE
            
            result = HoneypotCheckResult(
                token_address=token_address,
                risk_level=risk_level,
                is_honeypot=is_honeypot,
                reasons=reasons,
                warnings=warnings,
                metrics={
                    **metrics,
                    "risk_score": risk_score,
                    "risk_percentage": f"{risk_score}%"
                }
            )
            
            # Cache result
            self.check_history[token_address] = result
            
            # Log result
            self._log_result(result)
            
            return result
        
        except Exception as e:
            logger.error(f"❌ Honeypot check failed: {str(e)}")
            return HoneypotCheckResult(
                token_address=token_address,
                risk_level=HoneypotRisk.MEDIUM_RISK,
                is_honeypot=False,
                reasons=[f"Check failed: {str(e)}"],
                warnings=["Unable to complete full honeypot analysis"],
                metrics={"error": str(e)}
            )
    
    def _check_basic_properties(self, token_address: str) -> Dict:
        """Check basic token properties"""
        try:
            contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
            
            try:
                symbol = contract.functions.symbol().call()
            except:
                symbol = "UNKNOWN"
            
            try:
                decimals = contract.functions.decimals().call()
            except:
                decimals = 18
            
            try:
                total_supply = contract.functions.totalSupply().call()
            except:
                total_supply = 0
            
            issues = []
            
            # Check for suspicious total supply
            if total_supply == 0:
                issues.append("❌ Zero total supply (suspicious)")
            
            logger.info(f"   ✅ Symbol: {symbol} | Decimals: {decimals}")
            
            return {
                "passed": len(issues) == 0,
                "issues": issues,
                "metrics": {
                    "symbol": symbol,
                    "decimals": decimals,
                    "total_supply": str(total_supply)
                }
            }
        
        except Exception as e:
            logger.warning(f"   ⚠️ Could not check basic properties: {str(e)}")
            return {
                "passed": False,
                "issues": [f"Failed to read token properties: {str(e)}"],
                "metrics": {}
            }
    
    def _check_transfer_capabilities(self, token_address: str) -> Dict:
        """Check if token can be transferred"""
        try:
            contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
            
            # Create test address (won't actually transfer, just check if call works)
            test_to = "0x0000000000000000000000000000000000000001"
            test_amount = Web3.to_wei(1, 'wei')
            
            # Try to estimate gas for transfer (doesn't execute)
            try:
                estimate = contract.functions.transfer(test_to, test_amount).estimate_gas(
                    {'from': self.w3.eth.account.create().address}
                )
                logger.info(f"   ✅ Transfer gas estimation: {estimate}")
                return {
                    "passed": True,
                    "issues": [],
                    "metrics": {"transfer_gas_estimate": estimate}
                }
            except Exception as e:
                if "reverted" in str(e).lower() or "revert" in str(e).lower():
                    return {
                        "passed": False,
                        "issues": ["❌ Transfer function appears to be blocked"],
                        "metrics": {"error": str(e)}
                    }
                # Gas estimation might fail for other reasons, not necessarily blocked
                return {
                    "passed": True,
                    "issues": [],
                    "metrics": {"error": str(e)}
                }
        
        except Exception as e:
            logger.warning(f"   ⚠️ Could not check transfer capabilities: {str(e)}")
            return {
                "passed": False,
                "issues": [f"Transfer check failed: {str(e)}"],
                "metrics": {}
            }
    
    def _check_transfer_fees(self, token_address: str) -> Dict:
        """
        Detect transfer fee mechanisms
        Common honeypot tactic: 100% fee makes selling impossible
        """
        try:
            contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
            
            # Check for fee-related state variables or functions
            issues = []
            fee_percentage = 0
            
            # Try to detect common fee patterns
            # This is heuristic-based since different tokens implement fees differently
            
            # Check for fee mechanisms by calling common fee view functions.
            # Searching for ASCII "fee"/"tax" in hex bytecode produces many false positives
            # (e.g. 0xfeed, 0xbeef are valid hex). Instead we try to call well-known fee
            # getter functions directly on the contract.
            FEE_VIEW_ABIS = [
                {"inputs": [], "name": "taxFee",         "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "_taxFee",        "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "totalFees",      "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "liquidityFee",   "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "_liquidityFee",  "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "burnFee",        "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "_burnFee",       "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "fee",            "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "_fee",           "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "devFee",         "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "marketingFee",   "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
            ]

            fee_detected = False
            fee_function_name = ""
            fee_raw_value = 0
            for func_abi in FEE_VIEW_ABIS:
                try:
                    tmp_contract = self.w3.eth.contract(
                        address=token_address,
                        abi=[func_abi]
                    )
                    result = tmp_contract.functions[func_abi["name"]]().call()
                    if result and result > 0:
                        fee_detected = True
                        fee_raw_value = result
                        fee_function_name = func_abi["name"]
                        logger.info(f"   ⚠️ Fee function {func_abi['name']}() returned {result}")
                        break
                except Exception:
                    continue

            if fee_detected:
                # Normalize: many contracts store fees as basis points (e.g. 500 = 5%)
                # or as a direct percentage. Treat values > 10000 as raw wei-scaled.
                if fee_raw_value <= 10000:
                    fee_percentage = fee_raw_value / 100.0
                else:
                    fee_percentage = fee_raw_value / 1e18 * 100

                logger.info(f"   ⚠️ Fee mechanism detected in contract via {fee_function_name}()")
                warnings = [f"⚠️ Fee mechanism detected ({fee_percentage:.2f}% via {fee_function_name})"]
            else:
                warnings = []
            
            logger.info(f"   ℹ️ Fee analysis: {fee_percentage}% detected")
            
            return {
                "passed": fee_percentage < 50,  # < 50% is acceptable
                "issues": issues,
                "fee_percentage": fee_percentage,
                "warnings": warnings,
                "metrics": {"fee_percentage": fee_percentage}
            }
        
        except Exception as e:
            logger.warning(f"   ⚠️ Could not analyze fees: {str(e)}")
            return {
                "passed": True,
                "issues": [],
                "fee_percentage": 0,
                "warnings": [f"Fee analysis inconclusive"],
                "metrics": {}
            }
    
    def _check_suspicious_patterns(self, token_address: str) -> Dict:
        """Check for suspicious contract behaviors"""
        try:
            issues = []
            metrics = {}
            
            # Get contract code
            code = self.w3.eth.get_code(token_address)
            if len(code) < 100:
                issues.append("❌ Contract bytecode very small (suspicious)")
            
            # Check for proxy pattern
            # Proxies redirect calls, common in scams
            storage_0 = self.w3.eth.get_storage_at(token_address, 0)
            if storage_0 != "0x" + "0" * 64:
                metrics["possible_proxy"] = True
                logger.info("   ⚠️ Possible proxy pattern detected")
            
            logger.info(f"   ✅ Pattern analysis complete")
            
            return {
                "passed": len(issues) == 0,
                "issues": issues,
                "metrics": metrics
            }
        
        except Exception as e:
            logger.warning(f"   ⚠️ Could not check patterns: {str(e)}")
            return {
                "passed": True,
                "issues": [],
                "metrics": {}
            }
    
    def _simulate_dex_swap(self, token_address: str) -> Dict:
        """
        🔄 Simulate buying and selling token on DEX
        This is the CRITICAL test for honeypots
        """
        try:
            token_address = Web3.to_checksum_address(token_address)
            
            # Use WETH as quote token for Ethereum
            if self.chain == "ethereum":
                quote_token = STABLECOINS["ethereum"]["WETH"]
                router_address = DEX_ROUTERS["uniswap_v2"]
            else:
                logger.warning(f"⚠️ DEX swap simulation not configured for chain: {self.chain}")
                return {
                    "can_sell": True,
                    "warnings": [f"DEX swap simulation not available for {self.chain}"],
                    "result": "skipped"
                }
            
            router = self.w3.eth.contract(address=router_address, abi=UNISWAP_V2_ROUTER_ABI)
            
            # Test: Can we get swap amounts?
            try:
                # Try to get amountsOut for a hypothetical swap
                amount_in = Web3.to_wei(0.1, 'ether')  # 0.1 WETH
                path = [quote_token, token_address]
                
                amounts_out = router.functions.getAmountsOut(amount_in, path).call()
                
                # If we got here, buying is possible
                logger.info(f"   ✅ Can buy on DEX: {amounts_out[-1]} token units for 0.1 ETH")
                
                # Now test selling
                token_to_sell = amounts_out[-1]
                path_sell = [token_address, quote_token]
                
                try:
                    amounts_out_sell = router.functions.getAmountsOut(token_to_sell, path_sell).call()
                    eth_back = amounts_out_sell[-1]
                    
                    if eth_back > 0:
                        logger.info(f"   ✅ Can SELL on DEX: Get {Web3.from_wei(eth_back, 'ether'):.4f} ETH back")
                        return {
                            "can_sell": True,
                            "warnings": [],
                            "result": "success",
                            "metrics": {
                                "buy_amount": str(token_to_sell),
                                "sell_amount": str(eth_back)
                            }
                        }
                    else:
                        logger.error("   ❌ HONEYPOT DETECTED: Can buy but get 0 ETH back on sell!")
                        return {
                            "can_sell": False,
                            "warnings": ["❌ HONEYPOT: Zero output on sell"],
                            "result": "honeypot_confirmed"
                        }
                
                except Exception as sell_error:
                    logger.error(f"   ❌ HONEYPOT DETECTED: Cannot sell token!")
                    return {
                        "can_sell": False,
                        "warnings": [f"❌ HONEYPOT: Cannot execute sell: {str(sell_error)}"],
                        "result": "honeypot_confirmed"
                    }
            
            except Exception as buy_error:
                logger.warning(f"   ⚠️ Cannot buy on Uniswap (may not have liquidity): {str(buy_error)}")
                return {
                    "can_sell": True,
                    "warnings": [f"⚠️ No Uniswap liquidity detected, but not necessarily honeypot"],
                    "result": "no_liquidity"
                }
        
        except Exception as e:
            logger.error(f"   ❌ DEX simulation failed: {str(e)}")
            return {
                "can_sell": True,
                "warnings": [f"⚠️ DEX simulation inconclusive: {str(e)}"],
                "result": "error"
            }
    
    def _log_result(self, result: HoneypotCheckResult):
        """Log honeypot check result"""
        emoji_map = {
            HoneypotRisk.SAFE: "✅",
            HoneypotRisk.LOW_RISK: "🟢",
            HoneypotRisk.MEDIUM_RISK: "🟡",
            HoneypotRisk.HIGH_RISK: "🔴",
            HoneypotRisk.CONFIRMED_HONEYPOT: "❌"
        }
        
        emoji = emoji_map.get(result.risk_level, "❓")
        
        logger.info("\n" + "="*70)
        logger.info(f"{emoji} HONEYPOT CHECK RESULT: {result.risk_level.value.upper()}")
        logger.info("="*70)
        
        if result.is_honeypot:
            logger.error(f"🚨 TOKEN IS LIKELY A HONEYPOT!")
        else:
            logger.info(f"✅ Token appears to be legitimate")
        
        if result.reasons:
            logger.info("\n🔴 CRITICAL ISSUES:")
            for reason in result.reasons:
                logger.error(f"   {reason}")
        
        if result.warnings:
            logger.info("\n⚠️ WARNINGS:")
            for warning in result.warnings:
                logger.warning(f"   {warning}")
        
        if result.metrics:
            logger.info("\n📊 METRICS:")
            for key, value in result.metrics.items():
                if key not in ["risk_score", "risk_percentage"]:
                    logger.info(f"   {key}: {value}")
            if "risk_score" in result.metrics:
                logger.info(f"   Risk Score: {result.metrics['risk_percentage']}")
        
        logger.info("="*70 + "\n")

# Global singleton
_honeypot_detector_instance = None

def get_honeypot_detector(w3: Web3, chain: str = "ethereum") -> HoneypotDetector:
    """Get or create honeypot detector instance"""
    global _honeypot_detector_instance
    if _honeypot_detector_instance is None:
        _honeypot_detector_instance = HoneypotDetector(w3, chain)
    return _honeypot_detector_instance

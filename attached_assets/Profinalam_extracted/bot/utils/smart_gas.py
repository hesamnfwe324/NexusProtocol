"""
⛽ SMART GAS MANAGEMENT MODULE
Intelligent gas pricing for fastest execution
"""

import logging
import time
import statistics
from datetime import datetime, timedelta
from web3 import Web3
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class GasStrategy(Enum):
    EXTREME = "extreme"  # NEW: Maximum speed (50 Gwei base, 15x multiplier)
    ULTRA_FAST = "ultra_fast"
    FAST = "fast"
    NORMAL = "normal"
    ECONOMIC = "economic"
    ADAPTIVE = "adaptive"


@dataclass
class GasEstimate:
    """Gas price estimation result"""
    base_fee: int
    priority_fee: int
    max_fee: int
    legacy_gas_price: int
    strategy: GasStrategy
    confidence: float
    estimated_wait_seconds: int
    timestamp: str
    
    def to_dict(self) -> Dict:
        return {
            "base_fee_gwei": Web3.from_wei(self.base_fee, 'gwei'),
            "priority_fee_gwei": Web3.from_wei(self.priority_fee, 'gwei'),
            "max_fee_gwei": Web3.from_wei(self.max_fee, 'gwei'),
            "legacy_gas_gwei": Web3.from_wei(self.legacy_gas_price, 'gwei'),
            "strategy": self.strategy.value,
            "confidence": self.confidence,
            "estimated_wait_seconds": self.estimated_wait_seconds,
            "timestamp": self.timestamp
        }


class SmartGasOracle:
    """
    ⛽ SMART GAS ORACLE
    
    Features:
    - Real-time gas price monitoring
    - Historical analysis for prediction
    - Adaptive strategy based on network conditions
    - EIP-1559 optimization
    - Mempool analysis (when available)
    """
    
    def __init__(self, w3: Web3):
        self.w3 = w3
        self.gas_history: List[Dict] = []
        self.max_history_size = 1000
        
        self._monitoring = False
        self._monitor_thread = None
        
        self.strategy_multipliers = {
            GasStrategy.EXTREME: {"priority": 15.0, "max_fee": 8.0},  # NEW: Maximum
            GasStrategy.ULTRA_FAST: {"priority": 10.0, "max_fee": 5.0},
            GasStrategy.FAST: {"priority": 4.0, "max_fee": 3.0},
            GasStrategy.NORMAL: {"priority": 1.5, "max_fee": 1.8},
            GasStrategy.ECONOMIC: {"priority": 1.0, "max_fee": 1.2},
            GasStrategy.ADAPTIVE: {"priority": 2.0, "max_fee": 2.0},
        }
    
    def get_current_gas_prices(self) -> Dict:
        """Get current gas prices from the network"""
        try:
            latest_block = self.w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', 0)
            
            legacy_gas = self.w3.eth.gas_price
            
            pending_block = self.w3.eth.get_block('pending')
            pending_tx_count = len(pending_block.get('transactions', []))
            
            return {
                "base_fee": base_fee,
                "legacy_gas_price": legacy_gas,
                "pending_tx_count": pending_tx_count,
                "block_number": latest_block['number'],
                "block_gas_used": latest_block['gasUsed'],
                "block_gas_limit": latest_block['gasLimit'],
                "utilization": latest_block['gasUsed'] / latest_block['gasLimit'],
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting gas prices: {e}")
            return {
                "base_fee": 0,
                "legacy_gas_price": self.w3.eth.gas_price,
                "pending_tx_count": 0,
                "utilization": 0.5,
                "timestamp": datetime.now().isoformat()
            }
    
    def analyze_gas_trend(self) -> str:
        """Analyze recent gas price trend"""
        if len(self.gas_history) < 10:
            return "unknown"
        
        recent = self.gas_history[-10:]
        prices = [h['legacy_gas_price'] for h in recent]
        
        avg_first_half = statistics.mean(prices[:5])
        avg_second_half = statistics.mean(prices[5:])
        
        change_percent = ((avg_second_half - avg_first_half) / avg_first_half) * 100
        
        if change_percent > 20:
            return "rising_fast"
        elif change_percent > 5:
            return "rising"
        elif change_percent < -20:
            return "falling_fast"
        elif change_percent < -5:
            return "falling"
        else:
            return "stable"
    
    def estimate_optimal_gas(
        self, 
        strategy: GasStrategy = GasStrategy.FAST,
        max_gas_gwei: int = 200
    ) -> GasEstimate:
        """
        Estimate optimal gas price based on strategy
        """
        current = self.get_current_gas_prices()
        base_fee = current['base_fee']
        legacy_gas = current['legacy_gas_price']
        utilization = current.get('utilization', 0.5)
        
        multipliers = self.strategy_multipliers[strategy]
        
        if strategy == GasStrategy.ADAPTIVE:
            trend = self.analyze_gas_trend()
            if trend in ["rising_fast", "rising"]:
                multipliers = self.strategy_multipliers[GasStrategy.ULTRA_FAST]
            elif trend in ["falling_fast", "falling"]:
                multipliers = self.strategy_multipliers[GasStrategy.NORMAL]
            
            if utilization > 0.9:
                multipliers = {
                    "priority": multipliers["priority"] * 1.3,
                    "max_fee": multipliers["max_fee"] * 1.3
                }
        
        if base_fee > 0:
            base_priority = Web3.to_wei(2, 'gwei')
            
            priority_fee = int(base_priority * multipliers["priority"])
            max_fee = int(base_fee * multipliers["max_fee"]) + priority_fee
            
            max_allowed = Web3.to_wei(max_gas_gwei, 'gwei')
            max_fee = min(max_fee, max_allowed)
            priority_fee = min(priority_fee, max_fee)
        else:
            priority_fee = 0
            max_fee = 0
        
        adjusted_legacy = int(legacy_gas * multipliers["max_fee"])
        max_allowed = Web3.to_wei(max_gas_gwei, 'gwei')
        adjusted_legacy = min(adjusted_legacy, max_allowed)
        
        if strategy == GasStrategy.EXTREME:
            wait_time = 0
            confidence = 0.995
        elif strategy == GasStrategy.ULTRA_FAST:
            wait_time = 0
            confidence = 0.99
        elif strategy == GasStrategy.FAST:
            wait_time = 12
            confidence = 0.90
        elif strategy == GasStrategy.NORMAL:
            wait_time = 30
            confidence = 0.85
        else:
            wait_time = 60
            confidence = 0.75
        
        return GasEstimate(
            base_fee=base_fee,
            priority_fee=priority_fee,
            max_fee=max_fee,
            legacy_gas_price=adjusted_legacy,
            strategy=strategy,
            confidence=confidence,
            estimated_wait_seconds=wait_time,
            timestamp=datetime.now().isoformat()
        )
    
    def get_eip1559_params(
        self, 
        strategy: GasStrategy = GasStrategy.FAST,
        max_gas_gwei: int = 200
    ) -> Optional[Dict]:
        """Get EIP-1559 gas parameters"""
        estimate = self.estimate_optimal_gas(strategy, max_gas_gwei)
        
        if estimate.base_fee == 0:
            return None
        
        return {
            'maxFeePerGas': estimate.max_fee,
            'maxPriorityFeePerGas': estimate.priority_fee
        }
    
    def get_legacy_gas_price(
        self, 
        strategy: GasStrategy = GasStrategy.FAST,
        max_gas_gwei: int = 200
    ) -> int:
        """Get legacy gas price"""
        estimate = self.estimate_optimal_gas(strategy, max_gas_gwei)
        return estimate.legacy_gas_price
    
    def start_monitoring(self, interval: int = 5):
        """Start background gas monitoring"""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True
        )
        self._monitor_thread.start()
        logger.info("⛽ Gas monitoring started")
    
    def _monitor_loop(self, interval: int):
        """Background monitoring loop"""
        while self._monitoring:
            try:
                current = self.get_current_gas_prices()
                self.gas_history.append(current)
                
                if len(self.gas_history) > self.max_history_size:
                    self.gas_history = self.gas_history[-self.max_history_size:]
                
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Gas monitor error: {e}")
                time.sleep(interval * 2)
    
    def stop_monitoring(self):
        """Stop gas monitoring"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
    
    def get_statistics(self) -> Dict:
        """Get gas price statistics"""
        if not self.gas_history:
            return {"error": "No data available"}
        
        prices = [h['legacy_gas_price'] for h in self.gas_history]
        
        return {
            "current_gwei": Web3.from_wei(prices[-1], 'gwei'),
            "avg_gwei": Web3.from_wei(int(statistics.mean(prices)), 'gwei'),
            "min_gwei": Web3.from_wei(min(prices), 'gwei'),
            "max_gwei": Web3.from_wei(max(prices), 'gwei'),
            "std_dev_gwei": Web3.from_wei(int(statistics.stdev(prices)), 'gwei') if len(prices) > 1 else 0,
            "trend": self.analyze_gas_trend(),
            "samples": len(prices)
        }

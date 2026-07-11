"""
🔀 TRANSACTION ROUTER - ADVANCED ON-CHAIN ROUTING ENGINE
Optimizes transaction paths for privacy and cost efficiency
"""

import logging
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from web3 import Web3
import secrets

logger = logging.getLogger(__name__)


class RoutingOptimization(Enum):
    """Optimization goals"""
    MAX_PRIVACY = "max_privacy"
    MIN_COST = "min_cost"
    BALANCED = "balanced"
    MAX_SPEED = "max_speed"


@dataclass
class RouteNode:
    """A node in a transaction route"""
    address: str
    node_type: str  # "source" | "intermediate" | "destination" | "pool"
    expected_balance_before: float
    expected_balance_after: float
    expected_delay_seconds: int
    expected_fee_eth: float
    is_contract: bool = False


@dataclass
class RoutingMetrics:
    """Metrics for a routing path"""
    total_privacy_score: float  # 0-100
    total_cost_eth: float
    total_delay_seconds: int
    hops: int
    is_feasible: bool
    risk_level: str  # "low" | "medium" | "high"
    detailed_analysis: Dict = None


class TransactionRouter:
    """
    🔀 Advanced Transaction Routing Engine
    
    Capabilities:
    - Multi-hop transaction routing
    - Cost vs. Privacy optimization
    - Gas-efficient path finding
    - Real-time feasibility checking
    - Attribution pattern avoidance
    """
    
    def __init__(self, w3: Web3, privacy_masking=None):
        self.w3 = w3
        self.privacy_masking = privacy_masking
        
        # Cache for analyzed paths
        self.path_cache: Dict[str, RoutingMetrics] = {}
        self.recent_routes: List[Tuple[datetime, str, str]] = []
        
        # Blacklist for problematic routes
        self.problematic_routes: set = set()
        
        self.config = {
            "max_hops": 5,
            "min_hops": 1,
            "max_route_age_minutes": 30,
            "enable_pool_routing": True,
            "privacy_weight": 0.5,
            "cost_weight": 0.3,
            "speed_weight": 0.2,
        }
        
        logger.info("Transaction Router initialized")
    
    def plan_route(
        self,
        source: str,
        destination: str,
        amount: float,
        token_address: str,
        optimization: RoutingOptimization = RoutingOptimization.BALANCED
    ) -> Tuple[List[RouteNode], RoutingMetrics]:
        """Plan optimal transaction route"""
        
        # Check cache
        cache_key = f"{source}→{destination}:{optimization.value}"
        if cache_key in self.path_cache:
            cached_route = self.path_cache[cache_key]
            if self._is_cache_valid(cache_key):
                logger.info(f"Using cached route: {cache_key}")
                return self._reconstruct_route(source, destination), cached_route
        
        # Generate candidate routes
        candidates = self._generate_candidate_routes(source, destination, amount)
        
        # Score and rank candidates
        scored = []
        for route in candidates:
            metrics = self._evaluate_route(
                route, source, destination, amount, optimization
            )
            if metrics.is_feasible:
                scored.append((route, metrics))
        
        if not scored:
            logger.error(f"No feasible routes found for {source}→{destination}")
            return [], RoutingMetrics(0, 0, 0, 0, False, "high")
        
        # Select best route based on optimization
        best_route, best_metrics = self._select_best_route(scored, optimization)
        
        # Cache result
        self.path_cache[cache_key] = best_metrics
        self.recent_routes.append((datetime.now(), source, destination))
        
        logger.info(f"Planned route {source[:10]}→{destination[:10]} "
                   f"(hops: {len(best_route)}, privacy: {best_metrics.total_privacy_score:.0f}/100)")
        
        return best_route, best_metrics
    
    def _generate_candidate_routes(
        self,
        source: str,
        destination: str,
        amount: float
    ) -> List[List[str]]:
        """Generate candidate routing paths"""
        candidates = []
        
        # Route 1: Direct path (if privacy_masking available)
        candidates.append([source, destination])
        
        # Route 2-4: Multi-hop paths using address pool
        if self.privacy_masking and self.privacy_masking.address_pool:
            pool_addresses = list(self.privacy_masking.address_pool.keys())
            
            # 2-hop route
            if len(pool_addresses) > 0:
                intermediate = pool_addresses[secrets.randbelow(len(pool_addresses))]
                candidates.append([source, intermediate, destination])
            
            # 3-hop route
            if len(pool_addresses) > 1:
                intermediate1 = pool_addresses[secrets.randbelow(len(pool_addresses))]
                intermediate2 = pool_addresses[secrets.randbelow(len(pool_addresses))]
                candidates.append([source, intermediate1, intermediate2, destination])
            
            # Random 4-hop route
            if len(pool_addresses) > 2:
                intermediates = secrets.SystemRandom().sample(pool_addresses, min(2, len(pool_addresses)))
                candidates.append([source] + intermediates + [destination])
        
        # Route 5: Liquidity pool routing
        if self.config["enable_pool_routing"]:
            candidates.append([source, "UNISWAP_V3_POOL", destination])
        
        # Remove duplicates
        unique = []
        for candidate in candidates:
            if candidate not in unique and len(unique) < self.config["max_hops"]:
                unique.append(candidate)
        
        return unique
    
    def _evaluate_route(
        self,
        route: List[str],
        source: str,
        destination: str,
        amount: float,
        optimization: RoutingOptimization
    ) -> RoutingMetrics:
        """Evaluate a routing path"""
        
        # Calculate privacy score
        privacy_score = self._calculate_privacy_score(route, amount)
        
        # Estimate cost
        estimated_cost = self._estimate_route_cost(route)
        
        # Estimate time
        estimated_time = self._estimate_route_time(route)
        
        # Check feasibility
        is_feasible = self._check_route_feasibility(route, amount)
        
        # Determine risk
        risk_level = self._assess_risk_level(route, privacy_score)
        
        # Create metrics
        metrics = RoutingMetrics(
            total_privacy_score=privacy_score,
            total_cost_eth=estimated_cost,
            total_delay_seconds=estimated_time,
            hops=len(route),
            is_feasible=is_feasible,
            risk_level=risk_level
        )
        
        return metrics
    
    def _calculate_privacy_score(self, route: List[str], amount: float) -> float:
        """Calculate privacy effectiveness score (0-100)"""
        base_score = 50.0  # Start at 50
        
        # Add points for each hop
        hop_bonus = min(30.0, (len(route) - 1) * 10)
        base_score += hop_bonus
        
        # Bonus for using address pool
        if self.privacy_masking:
            pool_hops = sum(1 for addr in route if addr in self.privacy_masking.address_pool)
            pool_bonus = min(15.0, pool_hops * 5)
            base_score += pool_bonus
        
        # Complexity bonus
        if "POOL" in "".join(route):
            base_score += 5.0
        
        return min(100.0, base_score)
    
    def _estimate_route_cost(self, route: List[str]) -> float:
        """Estimate total ETH cost for route"""
        # Base gas cost per hop
        base_gas_per_hop = 21000  # Standard transfer
        
        # Variable gas based on route complexity
        if len(route) == 1:
            gas = base_gas_per_hop
        elif "POOL" in "".join(route):
            gas = base_gas_per_hop * 3  # Pool operations cost more
        else:
            gas = base_gas_per_hop * len(route) * 0.8  # Multi-hop transfers
        
        # Get current gas price
        try:
            gas_price = self.w3.eth.gas_price
        except:
            gas_price = int(20 * 1e9)  # Fallback: 20 Gwei
        
        cost_eth = (gas * gas_price) / 1e18
        return cost_eth
    
    def _estimate_route_time(self, route: List[str]) -> int:
        """Estimate total time in seconds"""
        if len(route) == 1:
            return 30
        
        # ~15 seconds per hop for confirmation
        base_time = 30 + ((len(route) - 1) * 15)
        
        # Add randomness to avoid patterns
        variance = secrets.randbelow(20)
        return base_time + variance
    
    def _check_route_feasibility(self, route: List[str], amount: float) -> bool:
        """Check if route is feasible"""
        # Check for obviously broken routes
        if len(route) == 0:
            return False
        
        # Check for repeated addresses (invalid path)
        if len(route) != len(set(route)):
            return False
        
        # Check if source and destination are different
        if route[0] == route[-1]:
            return False
        
        # Check against problematic routes
        route_key = "→".join(route)
        if route_key in self.problematic_routes:
            return False
        
        return True
    
    def _assess_risk_level(self, route: List[str], privacy_score: float) -> str:
        """Assess risk level of route"""
        if privacy_score < 40:
            return "high"
        elif privacy_score < 70:
            return "medium"
        else:
            return "low"
    
    def _select_best_route(
        self,
        scored: List[Tuple[List[str], RoutingMetrics]],
        optimization: RoutingOptimization
    ) -> Tuple[List[str], RoutingMetrics]:
        """Select best route based on optimization goal"""
        
        if optimization == RoutingOptimization.MAX_PRIVACY:
            best = max(scored, key=lambda x: x[1].total_privacy_score)
        elif optimization == RoutingOptimization.MIN_COST:
            best = min(scored, key=lambda x: x[1].total_cost_eth)
        elif optimization == RoutingOptimization.MAX_SPEED:
            best = min(scored, key=lambda x: x[1].total_delay_seconds)
        else:  # BALANCED
            best = max(scored, key=lambda x: self._calculate_balance_score(x[1]))
        
        return best[0], best[1]
    
    def _calculate_balance_score(self, metrics: RoutingMetrics) -> float:
        """Calculate balanced optimization score"""
        privacy_score = metrics.total_privacy_score / 100
        cost_score = 1 - min(1.0, metrics.total_cost_eth / 0.01)  # Normalize to 0.01 ETH
        speed_score = 1 - min(1.0, metrics.total_delay_seconds / 300)  # Normalize to 5 min
        
        return (
            privacy_score * self.config["privacy_weight"] +
            cost_score * self.config["cost_weight"] +
            speed_score * self.config["speed_weight"]
        )
    
    def _reconstruct_route(self, source: str, destination: str) -> List[RouteNode]:
        """Reconstruct detailed route from cache"""
        return [
            RouteNode(
                address=source,
                node_type="source",
                expected_balance_before=0,
                expected_balance_after=0,
                expected_delay_seconds=0,
                expected_fee_eth=0
            ),
            RouteNode(
                address=destination,
                node_type="destination",
                expected_balance_before=0,
                expected_balance_after=0,
                expected_delay_seconds=30,
                expected_fee_eth=0
            )
        ]
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached route is still valid"""
        # Cache valid for max_route_age_minutes
        return True  # Simplified for now
    
    def report_route_failure(self, source: str, destination: str) -> None:
        """Report failed route for learning"""
        route_key = f"{source}→{destination}"
        self.problematic_routes.add(route_key)
        logger.warning(f"Reported problematic route: {route_key}")
    
    def get_routing_statistics(self) -> Dict:
        """Get routing statistics"""
        return {
            "total_routes_cached": len(self.path_cache),
            "recent_routes": len(self.recent_routes),
            "problematic_routes": len(self.problematic_routes),
            "routes_executed": [(dt.isoformat(), src[:10], dst[:10]) for dt, src, dst in self.recent_routes[-10:]]
        }

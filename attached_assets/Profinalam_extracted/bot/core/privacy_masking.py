"""
🔐 ADVANCED ON-CHAIN PRIVACY MASKING MODULE
Prevents address clustering, breaks transaction chains, and reduces attribution
"""

import logging
import time
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum
from web3 import Web3
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [PRIVACY] %(message)s',
    handlers=[
        logging.FileHandler('privacy_masking.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AddressMixingStrategy(Enum):
    """Different address mixing strategies"""
    SEQUENTIAL_ROTATION = "sequential_rotation"
    RANDOM_SELECTION = "random_selection"
    TIME_BASED_ROTATION = "time_based_rotation"
    WEIGHTED_DISTRIBUTION = "weighted_distribution"
    CLUSTERING_AVOIDANCE = "clustering_avoidance"


class ChainBreakingStrategy(Enum):
    """Different chain-breaking approaches"""
    MULTI_HOP_TRANSFER = "multi_hop_transfer"
    DELAYED_FORWARDING = "delayed_forwarding"
    AMOUNT_SPLITTING = "amount_splitting"
    MIXED_ROUTING = "mixed_routing"
    LIQUIDITY_POOL_ROUTING = "liquidity_pool_routing"


@dataclass
class AddressProfile:
    """Profile of an address for privacy tracking"""
    address: str
    created_at: datetime
    last_used: datetime
    tx_count: int = 0
    total_volume_usd: float = 0.0
    is_active: bool = True
    nonce: int = 0
    age_hours: float = 0.0
    activity_signature: str = ""
    
    def get_clustering_risk(self) -> float:
        """Calculate clustering risk (0-1)"""
        # Risk increases if: young age, similar nonce, high volume
        age_risk = max(0, 1.0 - (self.age_hours / 168))  # High risk if < 1 week
        volume_risk = min(1.0, self.total_volume_usd / 100000)  # Scale to USD
        nonce_risk = min(1.0, self.nonce / 50)
        return (age_risk * 0.4 + volume_risk * 0.35 + nonce_risk * 0.25)


@dataclass
class TransactionPath:
    """A transaction routing path"""
    hops: List[str]  # Sequence of addresses
    total_hops: int
    estimated_time_minutes: float
    total_fee_impact: float
    attribution_reduction: float  # 0-1 score
    breakage_level: str  # "light" | "medium" | "heavy"
    path_id: str = ""
    
    def calculate_complexity_score(self) -> float:
        """Score the complexity of this path (higher = less trackable)"""
        hop_score = min(1.0, self.total_hops / 5)  # Normalize to 5+ hops
        time_score = min(1.0, self.estimated_time_minutes / 60)  # Spread over time
        fee_score = min(1.0, self.total_fee_impact / 0.1)  # Non-zero fees harder to trace
        return (hop_score * 0.4 + time_score * 0.35 + fee_score * 0.25)


class PrivacyMasking:
    """
    🔐 Advanced Privacy Masking System
    
    Features:
    - Address Clustering Prevention: Rotate through addresses, avoid patterns
    - Chain Breaking: Multi-hop transfers with randomized paths
    - Attribution Reduction: Obscure transaction relationships
    - Transaction Path Optimization: Maximize privacy vs. cost tradeoff
    """
    
    def __init__(self, w3: Web3, executor_private_key: str):
        self.w3 = w3
        self.executor_private_key = executor_private_key
        
        # Address pool for mixing
        self.address_pool: Dict[str, AddressProfile] = {}
        self.address_usage_history: Dict[str, List[datetime]] = {}
        self.transaction_graph: Dict[str, Set[str]] = {}  # Track relationships
        
        # Configuration
        self.config = {
            "max_nonce_diff_before_clustering": 10,
            "min_time_between_address_use_seconds": 60,
            "clustering_risk_threshold": 0.6,
            "default_mixing_strategy": AddressMixingStrategy.CLUSTERING_AVOIDANCE,
            "default_chain_breaking": ChainBreakingStrategy.MULTI_HOP_TRANSFER,
        }
        
        logger.info("Privacy Masking System initialized")
    
    # ==================== ADDRESS CLUSTERING PREVENTION ====================
    
    def register_address(self, address: str) -> AddressProfile:
        """Register a new address for mixing pool"""
        if address in self.address_pool:
            return self.address_pool[address]
        
        profile = AddressProfile(
            address=address,
            created_at=datetime.now(),
            last_used=datetime.now(),
            activity_signature=self._generate_activity_signature(address)
        )
        self.address_pool[address] = profile
        self.address_usage_history[address] = []
        self.transaction_graph[address] = set()
        
        logger.info(f"Registered address for mixing: {address[:10]}...")
        return profile
    
    def select_mixing_address(
        self,
        strategy: Optional[AddressMixingStrategy] = None,
        excluded_addresses: Optional[List[str]] = None
    ) -> Tuple[str, AddressProfile]:
        """Select next address using privacy strategy"""
        strategy = strategy or self.config["default_mixing_strategy"]
        excluded = set(excluded_addresses or [])
        
        available = {
            addr: profile for addr, profile in self.address_pool.items()
            if addr not in excluded and profile.is_active
        }
        
        if not available:
            raise ValueError("No available addresses for mixing")
        
        if strategy == AddressMixingStrategy.SEQUENTIAL_ROTATION:
            selected = self._select_sequential(available)
        elif strategy == AddressMixingStrategy.RANDOM_SELECTION:
            selected = self._select_random(available)
        elif strategy == AddressMixingStrategy.TIME_BASED_ROTATION:
            selected = self._select_time_based(available)
        elif strategy == AddressMixingStrategy.WEIGHTED_DISTRIBUTION:
            selected = self._select_weighted(available)
        elif strategy == AddressMixingStrategy.CLUSTERING_AVOIDANCE:
            selected = self._select_clustering_aware(available)
        else:
            selected = self._select_random(available)
        
        address, profile = selected
        profile.last_used = datetime.now()
        self.address_usage_history[address].append(datetime.now())
        
        logger.info(f"Selected mixing address: {address[:10]}... (clustering risk: {profile.get_clustering_risk():.2f})")
        return address, profile
    
    def _select_sequential(self, available: Dict[str, AddressProfile]) -> Tuple[str, AddressProfile]:
        """Select based on least recently used"""
        sorted_by_use = sorted(available.items(), key=lambda x: x[1].last_used)
        return sorted_by_use[0]
    
    def _select_random(self, available: Dict[str, AddressProfile]) -> Tuple[str, AddressProfile]:
        """Random selection with replacement"""
        addresses = list(available.items())
        return addresses[secrets.randbelow(len(addresses))]
    
    def _select_time_based(self, available: Dict[str, AddressProfile]) -> Tuple[str, AddressProfile]:
        """Select based on time window (avoid patterns)"""
        current_hour = datetime.now().hour
        candidates = [
            (addr, profile) for addr, profile in available.items()
            if len(self.address_usage_history[addr]) == 0 or
               (datetime.now() - profile.last_used).total_seconds() >= self.config["min_time_between_address_use_seconds"]
        ]
        if not candidates:
            candidates = list(available.items())
        return candidates[secrets.randbelow(len(candidates))]
    
    def _select_weighted(self, available: Dict[str, AddressProfile]) -> Tuple[str, AddressProfile]:
        """Weighted selection inversely proportional to usage"""
        weights = {}
        for addr, profile in available.items():
            # Prefer less-used addresses
            weight = 1.0 / (profile.tx_count + 1)
            weights[addr] = weight
        
        total_weight = sum(weights.values())
        normalized = {addr: w / total_weight for addr, w in weights.items()}
        
        r = secrets.random()
        cumsum = 0
        for addr, weight in normalized.items():
            cumsum += weight
            if r <= cumsum:
                return addr, available[addr]
        
        return list(available.items())[0]
    
    def _select_clustering_aware(self, available: Dict[str, AddressProfile]) -> Tuple[str, AddressProfile]:
        """Select address that minimizes clustering risk"""
        # Find address with lowest clustering risk
        best = min(available.items(), key=lambda x: x[1].get_clustering_risk())
        return best
    
    def analyze_clustering_risk(self) -> Dict[str, float]:
        """Analyze clustering risk for all registered addresses"""
        risks = {}
        for addr, profile in self.address_pool.items():
            risks[addr] = profile.get_clustering_risk()
        return risks
    
    # ==================== CHAIN BREAKING MECHANISMS ====================
    
    def generate_transaction_path(
        self,
        from_address: str,
        to_address: str,
        token_amount: float,
        strategy: Optional[ChainBreakingStrategy] = None,
        max_time_minutes: int = 120
    ) -> TransactionPath:
        """Generate a privacy-optimized transaction path"""
        strategy = strategy or self.config["default_chain_breaking"]
        
        if strategy == ChainBreakingStrategy.MULTI_HOP_TRANSFER:
            return self._generate_multihop_path(from_address, to_address, token_amount)
        elif strategy == ChainBreakingStrategy.DELAYED_FORWARDING:
            return self._generate_delayed_path(from_address, to_address, token_amount, max_time_minutes)
        elif strategy == ChainBreakingStrategy.AMOUNT_SPLITTING:
            return self._generate_split_path(from_address, to_address, token_amount)
        elif strategy == ChainBreakingStrategy.MIXED_ROUTING:
            return self._generate_mixed_path(from_address, to_address, token_amount)
        elif strategy == ChainBreakingStrategy.LIQUIDITY_POOL_ROUTING:
            return self._generate_pool_path(from_address, to_address, token_amount)
        else:
            return self._generate_multihop_path(from_address, to_address, token_amount)
    
    def _generate_multihop_path(self, from_addr: str, to_addr: str, amount: float) -> TransactionPath:
        """Multi-hop chain with intermediate addresses"""
        num_hops = secrets.randbelow(3) + 2  # 2-4 hops
        hops = [from_addr]
        
        # Add intermediate hops using address pool
        for _ in range(num_hops - 1):
            available = [
                a for a in self.address_pool.keys()
                if a != from_addr and a != to_addr and a not in hops
            ]
            if available:
                hops.append(available[secrets.randbelow(len(available))])
        
        hops.append(to_addr)
        
        path = TransactionPath(
            hops=hops,
            total_hops=len(hops),
            estimated_time_minutes=float(num_hops * secrets.randbelow(30) + 10),
            total_fee_impact=0.002 * (num_hops - 1),  # 0.2% per hop
            attribution_reduction=0.7 + (0.1 * num_hops),
            breakage_level="medium"
        )
        path.path_id = self._generate_path_id(path)
        return path
    
    def _generate_delayed_path(self, from_addr: str, to_addr: str, amount: float, max_time: int) -> TransactionPath:
        """Delayed forwarding to break temporal patterns"""
        delay_minutes = secrets.randbelow(min(max_time, 120)) + 5
        
        path = TransactionPath(
            hops=[from_addr, to_addr],
            total_hops=2,
            estimated_time_minutes=float(delay_minutes),
            total_fee_impact=0.0,
            attribution_reduction=0.5,
            breakage_level="light"
        )
        path.path_id = self._generate_path_id(path)
        return path
    
    def _generate_split_path(self, from_addr: str, to_addr: str, amount: float) -> TransactionPath:
        """Amount splitting to obscure total value"""
        num_splits = secrets.randbelow(3) + 2  # 2-4 splits
        split_amounts = self._split_amount(amount, num_splits)
        
        path = TransactionPath(
            hops=[from_addr] + [to_addr] * num_splits,
            total_hops=num_splits + 1,
            estimated_time_minutes=float(num_splits * 15),
            total_fee_impact=0.0005 * num_splits,
            attribution_reduction=0.6 + (0.08 * num_splits),
            breakage_level="medium"
        )
        path.path_id = self._generate_path_id(path)
        return path
    
    def _generate_mixed_path(self, from_addr: str, to_addr: str, amount: float) -> TransactionPath:
        """Combined approach: hops + delays + splitting"""
        num_hops = secrets.randbelow(2) + 2  # 2-3 hops
        delay = secrets.randbelow(60) + 10
        
        hops = [from_addr]
        for _ in range(num_hops - 1):
            available = [a for a in self.address_pool.keys() if a != from_addr and a != to_addr]
            if available:
                hops.append(available[secrets.randbelow(len(available))])
        hops.append(to_addr)
        
        path = TransactionPath(
            hops=hops,
            total_hops=len(hops),
            estimated_time_minutes=float(delay + num_hops * 10),
            total_fee_impact=0.0015 * num_hops,
            attribution_reduction=0.75 + (0.05 * num_hops),
            breakage_level="heavy"
        )
        path.path_id = self._generate_path_id(path)
        return path
    
    def _generate_pool_path(self, from_addr: str, to_addr: str, amount: float) -> TransactionPath:
        """Route through liquidity pool to break direct path"""
        path = TransactionPath(
            hops=[from_addr, "LIQUIDITY_POOL_INTERMEDIATE", to_addr],
            total_hops=3,
            estimated_time_minutes=5.0,
            total_fee_impact=0.003,  # ~0.3% slippage
            attribution_reduction=0.65,
            breakage_level="light"
        )
        path.path_id = self._generate_path_id(path)
        return path
    
    # ==================== ATTRIBUTION REDUCTION ====================
    
    def randomize_amount(
        self,
        base_amount: float,
        variance_percent: float = 5.0,
        min_amount: Optional[float] = None
    ) -> float:
        """Add variance to amount to reduce attribution"""
        variance = (base_amount * variance_percent / 100) * (2 * secrets.random() - 1)
        randomized = base_amount + variance
        
        if min_amount and randomized < min_amount:
            randomized = base_amount
        
        logger.info(f"Randomized amount: {base_amount} → {randomized:.2f}")
        return randomized
    
    def add_random_delay(self, base_delay_seconds: int = 0, max_variance_seconds: int = 300) -> float:
        """Add random delay to break temporal patterns"""
        variance = secrets.randbelow(max_variance_seconds + 1)
        total_delay = base_delay_seconds + variance
        logger.info(f"Added random delay: {total_delay} seconds")
        return float(total_delay)
    
    def anonymize_amount_pattern(self, amounts: List[float]) -> List[float]:
        """Break recognizable amount patterns"""
        return [self.randomize_amount(amt, variance_percent=3.5) for amt in amounts]
    
    def track_transaction_relationship(self, from_addr: str, to_addr: str) -> None:
        """Track transaction relationships for clustering analysis"""
        if from_addr in self.transaction_graph:
            self.transaction_graph[from_addr].add(to_addr)
        if to_addr in self.transaction_graph:
            self.transaction_graph[to_addr].add(from_addr)
    
    def analyze_transaction_graph(self) -> Dict[str, int]:
        """Analyze clustering in transaction graph"""
        clustering = {}
        for addr, connections in self.transaction_graph.items():
            clustering[addr] = len(connections)
        return clustering
    
    def identify_cluster_candidates(self, similarity_threshold: float = 0.7) -> List[Set[str]]:
        """Identify potential address clusters"""
        # Use nonce, age, and behavior similarity
        clusters = []
        used = set()
        
        for addr1, profile1 in self.address_pool.items():
            if addr1 in used:
                continue
            
            cluster = {addr1}
            used.add(addr1)
            
            for addr2, profile2 in self.address_pool.items():
                if addr2 in used:
                    continue
                
                similarity = self._calculate_address_similarity(profile1, profile2)
                if similarity > similarity_threshold:
                    cluster.add(addr2)
                    used.add(addr2)
            
            if len(cluster) > 1:
                clusters.append(cluster)
        
        logger.warning(f"Identified {len(clusters)} potential address clusters")
        return clusters
    
    # ==================== UTILITY METHODS ====================
    
    def _generate_activity_signature(self, address: str) -> str:
        """Generate activity signature for address"""
        return hashlib.sha256(
            f"{address}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
    
    def _split_amount(self, total: float, num_splits: int) -> List[float]:
        """Split amount into parts with variance"""
        if num_splits == 1:
            return [total]
        
        parts = []
        remaining = total
        
        for i in range(num_splits - 1):
            # Random portion with minimum threshold
            portion = remaining * (0.2 + secrets.random() * 0.6)
            parts.append(portion)
            remaining -= portion
        
        parts.append(remaining)
        return parts
    
    def _calculate_address_similarity(self, profile1: AddressProfile, profile2: AddressProfile) -> float:
        """Calculate similarity between two addresses (0-1)"""
        nonce_diff = abs(profile1.nonce - profile2.nonce)
        age_diff = abs(profile1.age_hours - profile2.age_hours)
        volume_ratio = profile1.total_volume_usd / max(profile2.total_volume_usd, 1.0)
        
        nonce_similarity = max(0, 1.0 - (nonce_diff / 100))
        age_similarity = max(0, 1.0 - (age_diff / 24))
        volume_similarity = 1.0 / (1.0 + abs(volume_ratio - 1.0))
        
        return (nonce_similarity * 0.4 + age_similarity * 0.35 + volume_similarity * 0.25)
    
    def _generate_path_id(self, path: TransactionPath) -> str:
        """Generate unique path ID"""
        path_str = "→".join([addr[:8] for addr in path.hops])
        return hashlib.sha256(
            f"{path_str}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]
    
    # ==================== REPORTING ====================
    
    def generate_privacy_report(self) -> Dict:
        """Generate comprehensive privacy analysis report"""
        clustering_risks = self.analyze_clustering_risk()
        graph_clustering = self.analyze_transaction_graph()
        clusters = self.identify_cluster_candidates()
        
        avg_clustering_risk = (
            sum(clustering_risks.values()) / len(clustering_risks)
            if clustering_risks else 0
        )
        
        return {
            "timestamp": datetime.now().isoformat(),
            "total_addresses": len(self.address_pool),
            "active_addresses": sum(1 for p in self.address_pool.values() if p.is_active),
            "avg_clustering_risk": avg_clustering_risk,
            "address_clustering_risks": clustering_risks,
            "transaction_graph_density": graph_clustering,
            "detected_clusters": len(clusters),
            "cluster_details": [list(c) for c in clusters],
            "recommendations": self._generate_recommendations(avg_clustering_risk, clusters)
        }
    
    def _generate_recommendations(self, avg_risk: float, clusters: List[Set[str]]) -> List[str]:
        """Generate recommendations to improve privacy"""
        recommendations = []
        
        if avg_risk > 0.7:
            recommendations.append("High clustering risk detected - consider adding more diverse addresses")
        if len(clusters) > 0:
            recommendations.append(f"Identified {len(clusters)} clusters - separate address pools recommended")
        if len(self.address_pool) < 5:
            recommendations.append("Add more addresses to improve mixing security")
        
        return recommendations


# Singleton instance for module-level access
_privacy_instance: Optional[PrivacyMasking] = None


def get_privacy_masking(w3: Web3, private_key: str) -> PrivacyMasking:
    """Get or create privacy masking instance"""
    global _privacy_instance
    if _privacy_instance is None:
        _privacy_instance = PrivacyMasking(w3, private_key)
    return _privacy_instance

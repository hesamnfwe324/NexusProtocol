"""
🌐 MULTI-RPC MANAGER MODULE
Multiple RPC endpoints with failover and load balancing
"""

import logging
import time
import random
import threading
from datetime import datetime, timedelta
from web3 import Web3
try:
    from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
except ImportError:
    try:
        from web3.middleware import geth_poa_middleware
    except ImportError:
        geth_poa_middleware = None
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


class RPCStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DEAD = "dead"


@dataclass
class RPCEndpoint:
    """RPC endpoint configuration"""
    url: str
    name: str
    priority: int = 5
    weight: int = 1
    max_requests_per_second: int = 50
    timeout: int = 30
    is_archive: bool = False
    supports_trace: bool = False
    
    status: RPCStatus = field(default=RPCStatus.HEALTHY)
    latency_ms: float = 0
    success_count: int = 0
    failure_count: int = 0
    last_check: str = ""
    consecutive_failures: int = 0
    
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return self.success_count / total


ETHEREUM_MAINNET_RPCS = [
    RPCEndpoint(
        url="https://eth.llamarpc.com",
        name="LlamaRPC",
        priority=10,
        weight=2,
        max_requests_per_second=100,
        is_archive=True
    ),
    RPCEndpoint(
        url="https://ethereum.publicnode.com",
        name="PublicNode",
        priority=9,
        weight=2,
        max_requests_per_second=50
    ),
    RPCEndpoint(
        url="https://rpc.ankr.com/eth",
        name="Ankr",
        priority=8,
        weight=2,
        max_requests_per_second=30
    ),
    RPCEndpoint(
        url="https://eth.drpc.org",
        name="DRPC",
        priority=8,
        weight=1,
        max_requests_per_second=50
    ),
    RPCEndpoint(
        url="https://cloudflare-eth.com",
        name="Cloudflare",
        priority=7,
        weight=1,
        max_requests_per_second=20
    ),
    RPCEndpoint(
        url="https://eth-mainnet.public.blastapi.io",
        name="BlastAPI",
        priority=7,
        weight=1,
        max_requests_per_second=25
    ),
    RPCEndpoint(
        url="https://1rpc.io/eth",
        name="1RPC",
        priority=6,
        weight=1,
        max_requests_per_second=20
    ),
    RPCEndpoint(
        url="https://api.securerpc.com/v1",
        name="SecureRPC",
        priority=6,
        weight=1,
        max_requests_per_second=15
    ),
]

PREMIUM_RPCS = [
    {
        "provider": "Alchemy",
        "url_template": "https://eth-mainnet.g.alchemy.com/v2/{API_KEY}",
        "priority": 10,
        "max_rps": 300,
        "features": ["archive", "trace", "websocket"]
    },
    {
        "provider": "Infura",
        "url_template": "https://mainnet.infura.io/v3/{API_KEY}",
        "priority": 10,
        "max_rps": 100,
        "features": ["archive", "websocket"]
    },
    {
        "provider": "QuickNode",
        "url_template": "https://xxx.quiknode.pro/{API_KEY}",
        "priority": 10,
        "max_rps": 500,
        "features": ["archive", "trace", "websocket"]
    },
    {
        "provider": "Chainstack",
        "url_template": "https://ethereum-mainnet.core.chainstack.com/{API_KEY}",
        "priority": 9,
        "max_rps": 200,
        "features": ["archive", "websocket"]
    },
]


class MultiRPCManager:
    """
    🌐 MULTI-RPC MANAGER
    
    Features:
    - Multiple RPC endpoints with automatic failover
    - Load balancing across healthy endpoints
    - Health checking and monitoring
    - Automatic recovery of failed endpoints
    - Latency-based routing
    - Priority-based selection
    """
    
    def __init__(self, endpoints: List[RPCEndpoint] = None, 
                 custom_rpcs: List[str] = None):
        self.endpoints: List[RPCEndpoint] = endpoints or ETHEREUM_MAINNET_RPCS.copy()
        
        if custom_rpcs:
            for i, url in enumerate(custom_rpcs):
                self.endpoints.insert(0, RPCEndpoint(
                    url=url,
                    name=f"Custom_{i+1}",
                    priority=11,
                    weight=3
                ))
        
        self.connections: Dict[str, Web3] = {}
        self._primary_connection: Optional[Web3] = None
        
        self._monitoring = False
        self._monitor_thread = None
        self._lock = threading.Lock()
        
        self._init_connections()
        
        logger.info(f"🌐 Multi-RPC Manager initialized with {len(self.endpoints)} endpoints")
    
    def _init_connections(self):
        """Initialize connections to all endpoints"""
        for endpoint in self.endpoints:
            try:
                w3 = Web3(Web3.HTTPProvider(
                    endpoint.url,
                    request_kwargs={'timeout': endpoint.timeout}
                ))
                
                try:
                    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                except:
                    pass
                
                self.connections[endpoint.url] = w3
                
            except Exception as e:
                logger.warning(f"Failed to init {endpoint.name}: {e}")
                endpoint.status = RPCStatus.DEAD
    
    def _check_endpoint_health(self, endpoint: RPCEndpoint) -> bool:
        """Check if endpoint is healthy"""
        try:
            w3 = self.connections.get(endpoint.url)
            if not w3:
                return False
            
            start = time.time()
            block = w3.eth.block_number
            latency = (time.time() - start) * 1000
            
            endpoint.latency_ms = latency
            endpoint.success_count += 1
            endpoint.consecutive_failures = 0
            endpoint.last_check = datetime.now().isoformat()
            
            if latency < 500:
                endpoint.status = RPCStatus.HEALTHY
            elif latency < 2000:
                endpoint.status = RPCStatus.DEGRADED
            else:
                endpoint.status = RPCStatus.UNHEALTHY
            
            return True
            
        except Exception as e:
            endpoint.failure_count += 1
            endpoint.consecutive_failures += 1
            endpoint.last_check = datetime.now().isoformat()
            
            if endpoint.consecutive_failures >= 5:
                endpoint.status = RPCStatus.DEAD
            elif endpoint.consecutive_failures >= 3:
                endpoint.status = RPCStatus.UNHEALTHY
            else:
                endpoint.status = RPCStatus.DEGRADED
            
            logger.warning(f"❌ {endpoint.name} health check failed: {e}")
            return False
    
    def get_best_endpoint(self) -> Optional[RPCEndpoint]:
        """Get the best available endpoint"""
        with self._lock:
            healthy = [
                e for e in self.endpoints 
                if e.status in [RPCStatus.HEALTHY, RPCStatus.DEGRADED]
            ]
            
            if not healthy:
                for endpoint in self.endpoints:
                    if endpoint.status != RPCStatus.DEAD:
                        healthy.append(endpoint)
            
            if not healthy:
                self._recover_dead_endpoints()
                healthy = [e for e in self.endpoints if e.status != RPCStatus.DEAD]
            
            if not healthy:
                return None
            
            healthy.sort(key=lambda e: (-e.priority, e.latency_ms))
            
            return healthy[0]
    
    def get_connection(self) -> Optional[Web3]:
        """Get the best available Web3 connection"""
        endpoint = self.get_best_endpoint()
        if not endpoint:
            logger.error("No healthy RPC endpoints available!")
            return None
        
        return self.connections.get(endpoint.url)
    
    def execute_with_failover(
        self, 
        func: Callable,
        max_retries: int = 3
    ):
        """Execute a function with automatic failover"""
        errors = []
        
        for attempt in range(max_retries):
            endpoint = self.get_best_endpoint()
            if not endpoint:
                raise Exception("No RPC endpoints available")
            
            w3 = self.connections.get(endpoint.url)
            if not w3:
                continue
            
            try:
                result = func(w3)
                endpoint.success_count += 1
                return result
                
            except Exception as e:
                error_msg = f"{endpoint.name}: {str(e)}"
                errors.append(error_msg)
                logger.warning(f"RPC call failed on {endpoint.name}: {e}")
                
                endpoint.failure_count += 1
                endpoint.consecutive_failures += 1
                
                if endpoint.consecutive_failures >= 3:
                    endpoint.status = RPCStatus.UNHEALTHY
                
                time.sleep(0.5)
        
        raise Exception(f"All RPC endpoints failed: {errors}")
    
    def _recover_dead_endpoints(self):
        """Attempt to recover dead endpoints"""
        for endpoint in self.endpoints:
            if endpoint.status == RPCStatus.DEAD:
                if endpoint.url not in self.connections:
                    try:
                        w3 = Web3(Web3.HTTPProvider(
                            endpoint.url,
                            request_kwargs={'timeout': endpoint.timeout}
                        ))
                        self.connections[endpoint.url] = w3
                    except:
                        continue
                
                if self._check_endpoint_health(endpoint):
                    logger.info(f"✅ Recovered {endpoint.name}")
    
    def start_monitoring(self, interval: int = 30):
        """Start background health monitoring"""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True
        )
        self._monitor_thread.start()
        logger.info("🌐 RPC monitoring started")
    
    def _monitor_loop(self, interval: int):
        """Background monitoring loop"""
        while self._monitoring:
            try:
                for endpoint in self.endpoints:
                    self._check_endpoint_health(endpoint)
                    time.sleep(1)
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(interval)
    
    def stop_monitoring(self):
        """Stop health monitoring"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
    
    def get_status(self) -> Dict:
        """Get status of all endpoints"""
        return {
            "total_endpoints": len(self.endpoints),
            "healthy": len([e for e in self.endpoints if e.status == RPCStatus.HEALTHY]),
            "degraded": len([e for e in self.endpoints if e.status == RPCStatus.DEGRADED]),
            "unhealthy": len([e for e in self.endpoints if e.status == RPCStatus.UNHEALTHY]),
            "dead": len([e for e in self.endpoints if e.status == RPCStatus.DEAD]),
            "endpoints": [
                {
                    "name": e.name,
                    "status": e.status.value,
                    "latency_ms": round(e.latency_ms, 2),
                    "success_rate": f"{e.success_rate()*100:.1f}%",
                    "priority": e.priority
                }
                for e in sorted(self.endpoints, key=lambda x: -x.priority)
            ]
        }
    
    def add_premium_rpc(self, provider: str, api_key: str):
        """Add a premium RPC endpoint with API key"""
        for rpc in PREMIUM_RPCS:
            if rpc['provider'].lower() == provider.lower():
                url = rpc['url_template'].replace("{API_KEY}", api_key)
                endpoint = RPCEndpoint(
                    url=url,
                    name=rpc['provider'],
                    priority=rpc['priority'],
                    weight=3,
                    max_requests_per_second=rpc['max_rps'],
                    is_archive='archive' in rpc['features'],
                    supports_trace='trace' in rpc['features']
                )
                self.endpoints.insert(0, endpoint)
                
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 30}))
                self.connections[url] = w3
                
                logger.info(f"✅ Added premium RPC: {provider}")
                return True
        
        return False

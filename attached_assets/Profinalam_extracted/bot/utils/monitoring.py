"""
Comprehensive Monitoring System
مانیتورینگ جامع سیستم

Includes:
- Centralized Sentry error tracking
- Prometheus metrics collection
- Structured logging
- Health checks
- Performance monitoring
- Slack alerting
"""

import os
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from structlog import get_logger
import structlog

# ============================================================================
# SETUP STRUCTURED LOGGING
# ============================================================================

def setup_structured_logging():
    """Setup structured logging with JSON format"""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

# ============================================================================
# SETUP SENTRY
# ============================================================================

def setup_sentry():
    """Initialize Sentry for error tracking (Disabled by user)"""
    return

# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

class MetricsCollector:
    """Centralized metrics collection"""
    
    # Approval Detection Metrics
    approvals_detected = Counter(
        'approvals_detected_total',
        'Total approvals detected',
        ['token_symbol']
    )
    
    approvals_validated = Counter(
        'approvals_validated_total',
        'Total approvals validated',
        ['token_symbol', 'status']  # valid/invalid
    )
    
    # Execution Metrics
    transfers_executed = Counter(
        'transfers_executed_total',
        'Total transfers executed',
        ['token_symbol', 'status']  # success/failed
    )
    
    transfer_time = Histogram(
        'transfer_execution_seconds',
        'Transfer execution time',
        ['token_symbol'],
        buckets=(0.5, 1.0, 5.0, 10.0, 30.0, 60.0)
    )
    
    gas_cost = Histogram(
        'gas_cost_gwei',
        'Gas cost per transaction',
        ['token_symbol'],
        buckets=(10, 25, 50, 100, 250, 500, 1000)
    )
    
    # System Metrics
    active_workers = Gauge(
        'active_workers_count',
        'Number of active workers'
    )
    
    queue_size = Gauge(
        'pending_queue_size',
        'Number of pending approvals in queue'
    )
    
    wallet_balance = Gauge(
        'wallet_balance_eth',
        'Executor wallet balance in ETH'
    )
    
    rpc_calls = Counter(
        'rpc_calls_total',
        'Total RPC calls made',
        ['method', 'status']  # success/failed
    )
    
    rpc_latency = Histogram(
        'rpc_latency_ms',
        'RPC call latency in milliseconds',
        ['method'],
        buckets=(10, 50, 100, 500, 1000, 5000)
    )
    
    errors = Counter(
        'errors_total',
        'Total errors occurred',
        ['error_type', 'module']
    )
    
    # Health Metrics
    system_up = Gauge(
        'system_up',
        'System is running (1=up, 0=down)'
    )
    
    last_approval_time = Gauge(
        'last_approval_detection_timestamp',
        'Timestamp of last approval detection'
    )
    
    last_execution_time = Gauge(
        'last_transfer_execution_timestamp',
        'Timestamp of last transfer execution'
    )

# ============================================================================
# HEALTH CHECKER
# ============================================================================

class HealthStatus(Enum):
    """Health status enumeration"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    OFFLINE = "offline"

class HealthChecker:
    """System health checking"""
    
    def __init__(self):
        self.checks = {}
    
    def register_check(self, name: str, check_fn):
        """Register a health check function"""
        self.checks[name] = check_fn
    
    def check_all(self) -> Dict[str, Any]:
        """Run all health checks"""
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": "healthy",
            "checks": {}
        }
        
        for name, check_fn in self.checks.items():
            try:
                status = check_fn()
                results["checks"][name] = status
                
                if status.get("status") in ["warning", "critical"]:
                    results["overall_status"] = "warning" if results["overall_status"] == "healthy" else results["overall_status"]
                    if status.get("status") == "critical":
                        results["overall_status"] = "critical"
            
            except Exception as e:
                results["checks"][name] = {
                    "status": "critical",
                    "error": str(e)
                }
                results["overall_status"] = "critical"
        
        return results

# ============================================================================
# MONITORING EVENT LOGGER
# ============================================================================

class MonitoringLogger:
    """Log important events to monitoring system"""
    
    def __init__(self):
        self.logger = get_logger("monitoring")
    
    def log_approval_detected(self, approval_data: Dict[str, Any]):
        """Log approval detection event"""
        MetricsCollector.approvals_detected.labels(
            token_symbol=approval_data.get('token_symbol', 'unknown')
        ).inc()
        
        self.logger.info("approval_detected", **approval_data)
    
    def log_approval_validated(self, approval_data: Dict[str, Any], is_valid: bool):
        """Log approval validation result"""
        status = "valid" if is_valid else "invalid"
        
        MetricsCollector.approvals_validated.labels(
            token_symbol=approval_data.get('token_symbol', 'unknown'),
            status=status
        ).inc()
        
        self.logger.info("approval_validated", status=status, **approval_data)
    
    def log_transfer_execution(self, tx_hash: str, token_symbol: str, status: str, details: Dict):
        """Log transfer execution"""
        MetricsCollector.transfers_executed.labels(
            token_symbol=token_symbol,
            status=status
        ).inc()
        
        self.logger.info("transfer_executed", tx_hash=tx_hash, token=token_symbol, status=status, **details)
    
    def log_error(self, error_type: str, module: str, error: Exception, context: Dict = None):
        """Log error event"""
        MetricsCollector.errors.labels(
            error_type=error_type,
            module=module
        ).inc()
        
        self.logger.error("error_occurred", error_type=error_type, module=module, error=str(error), context=context)
    
    def log_rpc_call(self, method: str, duration_ms: float, success: bool):
        """Log RPC call metrics"""
        status = "success" if success else "failed"
        
        MetricsCollector.rpc_calls.labels(
            method=method,
            status=status
        ).inc()
        
        MetricsCollector.rpc_latency.labels(method=method).observe(duration_ms)
    
    def log_system_status(self, is_up: bool, details: Dict = None):
        """Log system status"""
        MetricsCollector.system_up.set(1 if is_up else 0)
        self.logger.info("system_status", is_up=is_up, details=details)

# ============================================================================
# SLACK ALERTING
# ============================================================================

def send_slack_alert(message: str, level: str = "info", details: Dict = None):
    """Send alert to Slack webhook"""
    # Also send to Telegram if configured
    send_telegram_alert(message, level, details)

    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    
    if not webhook_url:
        return
    
    import requests
    
    # Color based on level
    color_map = {
        "info": "#0099ff",
        "warning": "#ffaa00",
        "error": "#ff0000",
        "critical": "#cc0000"
    }
    
    payload = {
        "attachments": [
            {
                "color": color_map.get(level, "#0099ff"),
                "title": f"{level.upper()}: Blockchain Monitor Alert",
                "text": message,
                "ts": int(datetime.utcnow().timestamp()),
                "fields": [
                    {"title": f, "value": str(v), "short": True}
                    for f, v in (details or {}).items()
                ] if details else []
            }
        ]
    }
    
    try:
        requests.post(webhook_url, json=payload, timeout=5)
    except Exception as e:
        logging.error(f"Failed to send Slack alert: {e}")

# ============================================================================
# TELEGRAM ALERTING
# ============================================================================

def send_telegram_alert(message: str, level: str = "info", details: Dict = None):
    """Send alert to Telegram"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        return

    import requests
    import html

    emoji_map = {
        "info": "ℹ️",
        "warning": "⚠️",
        "error": "❌",
        "critical": "🚨"
    }

    icon = emoji_map.get(level, "ℹ️")
    # Escape HTML special characters in the message
    safe_message = html.escape(message)
    formatted_message = f"{icon} <b>{level.upper()}: Blockchain Monitor Alert</b>\n\n{safe_message}"
    
    if details:
        formatted_message += "\n\n<b>Details:</b>\n"
        for k, v in details.items():
            formatted_message += f"• {html.escape(str(k))}: {html.escape(str(v))}\n"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": formatted_message,
        "parse_mode": "HTML"
    }
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logging.error(f"Failed to send Telegram alert: {e}")


class TelegramLogHandler(logging.Handler):
    """Logging handler that sends logs to Telegram"""
    def __init__(self, token, chat_id):
        super().__init__()
        self.token = token
        self.chat_id = chat_id
        import requests
        self.requests = requests
        import html
        self.html = html

    def emit(self, record):
        try:
            msg = self.format(record)
            # Filter out some very verbose logs if needed, but user asked for "every action"
            # We can skip empty messages
            if not msg.strip():
                return
                
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            # Escape HTML characters for the log message
            safe_msg = self.html.escape(msg)
            
            payload = {
                "chat_id": self.chat_id,
                "text": f"<code>{safe_msg}</code>", # Monospace for logs
                "parse_mode": "HTML"
            }
            self.requests.post(url, json=payload, timeout=2)
        except Exception:
            self.handleError(record)


# ============================================================================
# INITIALIZATION
# ============================================================================

# Initialize monitoring systems
setup_structured_logging()
setup_sentry()

# Global instances
metrics = MetricsCollector()
health_checker = HealthChecker()
monitoring_logger = MonitoringLogger()

logging.info("✅ Comprehensive monitoring system initialized")

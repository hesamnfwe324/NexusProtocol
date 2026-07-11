"""
Health Check Endpoint
سلامت‌بررسی انقطه

Provides /health and /metrics endpoints for monitoring
"""

from flask import Flask, jsonify
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from utils.monitoring import health_checker, metrics
import os

def create_health_app():
    """Create Flask app for health checks and metrics"""
    app = Flask(__name__)
    
    @app.route('/health', methods=['GET'])
    def health():
        """Health check endpoint"""
        health_status = health_checker.check_all()
        status_code = 200 if health_status['overall_status'] == 'healthy' else 503
        return jsonify(health_status), status_code
    
    @app.route('/metrics', methods=['GET'])
    def metrics_endpoint():
        """Prometheus metrics endpoint"""
        return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}
    
    @app.route('/status', methods=['GET'])
    def status():
        """Quick status check"""
        return jsonify({
            "status": "running",
            "version": os.getenv("APP_VERSION", "1.0.0"),
            "environment": os.getenv("ENVIRONMENT", "development")
        }), 200
    
    return app

def run_health_server(port: int = 9000):
    """Run health check server in separate thread"""
    import threading
    
    app = create_health_app()
    
    def run_server():
        app.run(host='0.0.0.0', port=port, debug=False)
    
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    
    import logging
    logging.info(f"✅ Health check server started on port {port}")

"""
Flask REST API for Home Assistant to poll
"""
from flask import Flask, jsonify
from datetime import datetime
import threading


class RESTAPIServer:
    """Simple REST API for Home Assistant to poll"""

    def __init__(self, host: str = '0.0.0.0', port: int = 5000):
        """
        Initialize REST API server

        Args:
            host: Host to bind to (default: 0.0.0.0 for all interfaces)
            port: Port to listen on (default: 5000)
        """
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.bin_date = None
        self.last_update = None
        self._setup_routes()

    def _setup_routes(self):
        """Setup Flask routes"""

        @self.app.route('/api/bin-collection', methods=['GET'])
        def get_bin_collection():
            if not self.bin_date:
                return jsonify({"error": "No bin collection date available"}), 404

            return jsonify({
                "date": self.bin_date.strftime('%Y-%m-%d'),
                "day_of_week": self.bin_date.strftime('%A'),
                "days_until": (self.bin_date - datetime.now()).days,
                "last_update": self.last_update.isoformat() if self.last_update else None
            })

        @self.app.route('/api/health', methods=['GET'])
        def health_check():
            return jsonify({"status": "ok", "service": "blackbin-api"})

    def update_date(self, date: datetime):
        """Update the bin collection date"""
        self.bin_date = date
        self.last_update = datetime.now()
        print(f"[REST API] Updated bin date to {date.strftime('%Y-%m-%d')}")

    def start(self):
        """Start Flask server in background thread"""
        def run_server():
            # Disable Flask's default logging for cleaner output
            import logging
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.ERROR)

            self.app.run(host=self.host, port=self.port, debug=False, use_reloader=False)

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        print(f"[REST API] ✓ Server started on {self.host}:{self.port}")

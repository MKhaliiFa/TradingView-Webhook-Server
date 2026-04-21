"""
main.py — TradingView Webhook Server (Flask)

Receives authenticated POST signals from TradingView alerts and routes them
to the exchange handler for execution.
"""

import os
import logging
from flask import Flask, request, jsonify
from exchange_handler import execute_trade

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
# Use a structured format that includes timestamp, level, and module name.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("webhook_server")

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)

# Load the shared secret from the environment.  The server will refuse to
# start if this variable is not set so that misconfiguration is caught early.
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
if not WEBHOOK_SECRET:
    raise EnvironmentError(
        "WEBHOOK_SECRET environment variable is not set. "
        "Add it via the Replit Secrets tab before starting the server."
    )


# ---------------------------------------------------------------------------
# Health-check endpoint
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    """Simple liveness probe — no auth required."""
    return jsonify({"status": "ok"}), 200


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Accepts a JSON payload from a TradingView alert and executes the trade.

    Expected payload shape:
        {
            "token":  "<your-secret-token>",   # OR supply via X-TV-Token header
            "action": "buy" | "sell",
            "symbol": "BTCUSDT",
            "price":  "65000"
        }

    Authentication:
        The secret token may be supplied in two ways (header takes priority):
          1. HTTP header  — X-TV-Token: <secret>
          2. JSON field   — "token": "<secret>"

    Returns HTTP 200 on success, 400/401/500 otherwise.
    """
    # --- 1. Parse JSON body ---------------------------------------------------
    payload = request.get_json(silent=True)
    if payload is None:
        logger.warning("Received webhook with non-JSON or empty body.")
        return jsonify({"error": "Request body must be valid JSON."}), 400

    logger.info(
        "Incoming webhook — IP: %s  symbol: %s  action: %s  price: %s",
        request.remote_addr,
        payload.get("symbol", "<missing>"),
        payload.get("action", "<missing>"),
        payload.get("price", "<missing>"),
    )

    # --- 2. Authenticate ------------------------------------------------------
    # Header takes priority over body field.
    provided_token = request.headers.get("X-TV-Token") or payload.get("token")

    if not provided_token or provided_token != WEBHOOK_SECRET:
        logger.warning(
            "Authentication FAILED — invalid or missing token from IP: %s",
            request.remote_addr,
        )
        return jsonify({"error": "Unauthorized: invalid or missing token."}), 401

    # --- 3. Validate required fields ------------------------------------------
    action = payload.get("action")
    symbol = payload.get("symbol")
    price = payload.get("price")

    missing = [f for f, v in [("action", action), ("symbol", symbol), ("price", price)] if not v]
    if missing:
        logger.warning("Webhook rejected — missing fields: %s", missing)
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    # --- 4. Delegate to exchange handler --------------------------------------
    logger.info(
        "Signal authenticated — executing trade: action=%s  symbol=%s  price=%s",
        action,
        symbol,
        price,
    )

    result = execute_trade(action=action, symbol=symbol, price=price)

    logger.info("Trade execution result: %s", result)
    return jsonify({"status": "success", "result": result}), 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting TradingView webhook server on port %d …", port)
    # debug=False is mandatory in production.
    app.run(host="0.0.0.0", port=port, debug=False)

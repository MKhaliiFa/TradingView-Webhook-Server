"""
main.py — TradingView Webhook Server (Flask)

Receives authenticated POST signals from TradingView alerts, runs them through
the exchange handler, and exposes a real-time Bootstrap dashboard at /.
"""

import os
import hmac
import logging
import datetime
from collections import deque
from flask import Flask, request, jsonify, render_template, Response

from exchange_handler import execute_trade, TradeError

# ---------------------------------------------------------------------------
# In-memory log buffer (thread-safe circular queue, newest last)
# ---------------------------------------------------------------------------
MAX_LOG_ENTRIES = 200
_log_buffer: deque = deque(maxlen=MAX_LOG_ENTRIES)

LEVEL_COLORS = {
    "INFO":    "success",
    "WARNING": "warning",
    "ERROR":   "danger",
    "CRITICAL":"danger",
    "DEBUG":   "secondary",
}


class BufferHandler(logging.Handler):
    """Appends every log record to the in-memory deque for the /logs endpoint."""

    def emit(self, record: logging.LogRecord) -> None:
        ts = datetime.datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        _log_buffer.append({
            "ts":      ts,
            "level":   record.levelname,
            "color":   LEVEL_COLORS.get(record.levelname, "secondary"),
            "logger":  record.name,
            "message": self.format(record),
        })


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
_fmt = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# Suppress noisy polling routes from appearing in the dashboard and console.
# werkzeug access log lines look like: ... "GET /logs?since=5 HTTP/1.1" 200 -
_MUTED_PATTERNS = ('"GET /logs', '"GET /health', '"GET /favicon.ico')


class _MutePollingFilter(logging.Filter):
    """Drop werkzeug access-log entries for polling and housekeeping routes."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(pat in msg for pat in _MUTED_PATTERNS)


_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_fmt)

_buffer_handler = BufferHandler()
_buffer_handler.setFormatter(_fmt)

logging.basicConfig(handlers=[_console_handler, _buffer_handler], level=logging.INFO)
logger = logging.getLogger("webhook_server")

# Apply the filter to the werkzeug access logger specifically, so it only
# suppresses HTTP access lines — not application-level werkzeug warnings.
logging.getLogger("werkzeug").addFilter(_MutePollingFilter())

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
# Locate templates relative to this file so the server works regardless of
# the current working directory.
_here = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(_here, "templates"))

# Load and validate the shared secret at startup — fail fast if missing.
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()
if not WEBHOOK_SECRET:
    raise EnvironmentError(
        "WEBHOOK_SECRET environment variable is not set. "
        "Add it via the Replit Secrets tab before starting the server."
    )

# Record startup time for uptime display on the dashboard.
_start_time: datetime.datetime = datetime.datetime.utcnow()

logger.info("Webhook server initialised. Secret loaded, ready to accept signals.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uptime() -> str:
    """Return a human-readable uptime string."""
    delta = datetime.datetime.utcnow() - _start_time
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def _secure_compare(a: str, b: str) -> bool:
    """
    Constant-time string comparison to prevent timing-based token discovery.
    Uses hmac.compare_digest which is immune to short-circuit evaluation.
    """
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---------------------------------------------------------------------------
# Dashboard — root route
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def dashboard():
    """Render the Bootstrap status dashboard."""
    return render_template(
        "dashboard.html",
        uptime=_uptime(),
        start_time=_start_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        log_count=len(_log_buffer),
    )


# ---------------------------------------------------------------------------
# Favicon — served inline as a tiny SVG to suppress 404 log noise
# ---------------------------------------------------------------------------

_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
    '<rect width="16" height="16" rx="3" fill="#26a69a"/>'
    '<path d="M3 8 L6 5 L8 10 L10 6 L13 8" stroke="#fff" stroke-width="1.5"'
    ' fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>'
)


@app.route("/favicon.ico")
def favicon():
    return Response(_FAVICON_SVG, mimetype="image/svg+xml")


# ---------------------------------------------------------------------------
# Live logs API — polled by dashboard JavaScript
# ---------------------------------------------------------------------------

@app.route("/logs", methods=["GET"])
def logs():
    """
    Return recent log entries as JSON for the dashboard live-log panel.
    Query params:
      ?since=<index>  — return only entries newer than this zero-based index
    """
    try:
        since = int(request.args.get("since", 0))
    except (ValueError, TypeError):
        since = 0

    entries = list(_log_buffer)
    new_entries = entries[since:]
    return jsonify({
        "total": len(entries),
        "entries": new_entries,
    }), 200


# ---------------------------------------------------------------------------
# Health-check endpoint
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """Liveness probe — returns server status and uptime. No auth required."""
    return jsonify({
        "status":     "ok",
        "uptime":     _uptime(),
        "start_time": _start_time.isoformat() + "Z",
    }), 200


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Accepts a JSON payload from a TradingView alert and executes the trade.

    Expected payload:
        {
            "token":  "<secret>",      # OR via X-TV-Token header (header wins)
            "action": "buy" | "sell",
            "symbol": "BTCUSDT",
            "price":  "65000"
        }

    HTTP responses:
        200 — signal accepted and processed
        400 — malformed JSON or missing required fields
        401 — invalid or missing authentication token
        405 — wrong HTTP method (handled by Flask automatically)
        500 — unexpected error during trade execution
    """
    # ── 1. Parse body ────────────────────────────────────────────────────────
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        logger.warning(
            "Rejected webhook — non-JSON or empty body from IP: %s",
            request.remote_addr,
        )
        return jsonify({"error": "Request body must be a valid JSON object."}), 400

    # ── 2. Authenticate — constant-time comparison ───────────────────────────
    # Header takes priority; fall back to body field so both work with TradingView.
    provided_token = (request.headers.get("X-TV-Token") or payload.get("token", "")).strip()

    if not provided_token or not _secure_compare(provided_token, WEBHOOK_SECRET):
        logger.warning(
            "Authentication FAILED — invalid or missing token from IP: %s",
            request.remote_addr,
        )
        return jsonify({"error": "Unauthorized: invalid or missing token."}), 401

    # ── 3. Log after auth so unauthenticated noise is not polluted ────────────
    action = payload.get("action")
    symbol = payload.get("symbol")
    price  = payload.get("price")

    logger.info(
        "Signal received — IP: %s  action: %s  symbol: %s  price: %s",
        request.remote_addr, action, symbol, price,
    )

    # ── 4. Validate required fields ──────────────────────────────────────────
    # Use `is None` (not falsy) so that a price of "0" is not rejected.
    missing = [
        name for name, val in [("action", action), ("symbol", symbol), ("price", price)]
        if val is None
    ]
    if missing:
        logger.warning("Webhook rejected — missing fields: %s", missing)
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    # Validate action value
    if str(action).lower() not in ("buy", "sell"):
        logger.warning("Webhook rejected — invalid action value: %s", action)
        return jsonify({"error": "Field 'action' must be 'buy' or 'sell'."}), 400

    # ── 5. Execute trade ─────────────────────────────────────────────────────
    try:
        logger.info(
            "Executing trade — action: %s  symbol: %s  price: %s",
            action, symbol, price,
        )
        result = execute_trade(
            action=str(action).lower(),
            symbol=str(symbol),
            price=str(price),
        )
        logger.info("Trade execution result: %s", result)
        return jsonify({"status": "success", "result": result}), 200

    except TradeError as exc:
        # Known, structured error from the exchange handler
        logger.error("Trade execution failed (TradeError): %s", exc)
        return jsonify({"error": str(exc)}), 422

    except Exception as exc:
        # Unexpected error — log with full traceback, return safe 500
        logger.error("Unexpected error during trade execution: %s", exc, exc_info=True)
        return jsonify({"error": "Internal server error. Check server logs."}), 500


# ---------------------------------------------------------------------------
# Generic 404 / 405 JSON handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found."}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed."}), 405


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # PORT is set dynamically by Replit in production (defaults to 8080).
    # The development workflow passes PORT=5000 explicitly so Flask
    # does not conflict with the Express proxy server on 8080.
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting TradingView webhook server on host=0.0.0.0 port=%d …", port)
    app.run(host="0.0.0.0", port=port, debug=False)

"""main.py - TradingView -> MT5 EA Bridge.

A tiny Flask service that sits between TradingView alerts and an MT5 Expert
Advisor. It exposes two endpoints:

* POST /webhook     - receives authenticated TradingView alerts and persists
                      the signal payload to ``signal.json``.
* GET  /get_signal  - read-and-clear endpoint polled by the EA; returns the
                      stored signal (if any) and removes it so each signal
                      is delivered exactly once.

The bridge does no trade execution of its own. Execution is the EA's job.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
SIGNAL_FILE = Path(os.environ.get("SIGNAL_FILE", _HERE / "signal.json"))

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()
if not WEBHOOK_SECRET:
    raise EnvironmentError(
        "WEBHOOK_SECRET environment variable is not set. "
        "Set it before starting the server."
    )

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger("tv_mt5_bridge")

# ---------------------------------------------------------------------------
# App + concurrency guard
# ---------------------------------------------------------------------------

app = Flask(__name__)

# Serialises access to the signal file across Flask worker threads so a slow
# writer cannot race a concurrent reader and hand the EA half a document.
_signal_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _secure_compare(a: str, b: str) -> bool:
    """Constant-time string comparison for secret validation."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _write_signal(payload: dict[str, Any]) -> None:
    """Write the signal atomically via tmp-file + rename."""
    tmp_path = SIGNAL_FILE.with_suffix(SIGNAL_FILE.suffix + ".tmp")
    serialised = json.dumps(payload, ensure_ascii=False, indent=2)
    with _signal_lock:
        tmp_path.write_text(serialised, encoding="utf-8")
        os.replace(tmp_path, SIGNAL_FILE)


def _pop_signal() -> dict[str, Any] | None:
    """Read the stored signal and delete the file in one critical section."""
    with _signal_lock:
        if not SIGNAL_FILE.exists():
            return None
        try:
            data = json.loads(SIGNAL_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Corrupt signal file, discarding: %s", exc)
            SIGNAL_FILE.unlink(missing_ok=True) #
            return None
        SIGNAL_FILE.unlink(missing_ok=True)
        return data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.route("/webhook", methods=["POST"])
def webhook() -> Any:
    """Receive a TradingView alert, validate its secret, and store it."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        logger.warning(
            "Rejected /webhook - non-JSON body from %s", request.remote_addr
        )
        return jsonify({"error": "Request body must be a valid JSON object."}), 400

    # Accept the secret either via header (preferred) or body field.
    provided_token = (
        request.headers.get("X-TV-Token")
        or str(payload.get("token") or "")
    ).strip()

    if not provided_token or not _secure_compare(provided_token, WEBHOOK_SECRET):
        logger.warning(
            "Unauthorized /webhook attempt from %s", request.remote_addr
        )
        return jsonify({"error": "Unauthorized: invalid or missing token."}), 401

    # Strip the shared secret before persisting so it never hits disk.
    signal = {k: v for k, v in payload.items() if k != "token"}
    if not signal:
        return jsonify({"error": "Signal payload is empty."}), 400

    try:
        _write_signal(signal)
    except OSError as exc:
        logger.error("Failed to persist signal: %s", exc)
        return jsonify({"error": "Failed to store signal."}), 500

    logger.info("Signal stored for EA pickup: %s", signal)
    return jsonify({"status": "ok", "stored": True}), 200


@app.route("/get_signal", methods=["GET"])
def get_signal() -> Any:
    """Return the stored signal (if any) and clear it for exactly-once delivery."""
    signal = _pop_signal()
    if signal is None:
        return jsonify({"status": "empty", "signal": None}), 200

    logger.info("Signal dispatched to EA: %s", signal)
    return jsonify({"status": "ok", "signal": signal}), 200


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def _not_found(_: Exception) -> Any:
    return jsonify({"error": "Not found."}), 404


@app.errorhandler(405)
def _method_not_allowed(_: Exception) -> Any:
    return jsonify({"error": "Method not allowed."}), 405


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting TradingView -> MT5 bridge on 0.0.0.0:%d", port)
    app.run(host="0.0.0.0", port=port, debug=False)

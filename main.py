"""main.py - TradingView -> MT5 EA Bridge with Telegram.

A tiny Flask service that sits between TradingView alerts and an MT5 Expert
Advisor. It exposes two endpoints:

* POST /webhook     - receives authenticated TradingView alerts, persists
                      the signal, and sends a formatted Telegram alert.
* GET  /get_signal  - read endpoint polled by the EA. File deletion is disabled 
                      to allow multiple MT5 terminals to read the same signal.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import threading
import requests  
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
_signal_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _secure_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))

def _write_signal(payload: dict[str, Any]) -> None:
    tmp_path = SIGNAL_FILE.with_suffix(SIGNAL_FILE.suffix + ".tmp")
    serialised = json.dumps(payload, ensure_ascii=False, indent=2)
    with _signal_lock:
        tmp_path.write_text(serialised, encoding="utf-8")
        os.replace(tmp_path, SIGNAL_FILE)

def _pop_signal() -> dict[str, Any] | None:
    with _signal_lock:
        if not SIGNAL_FILE.exists():
            return None
        try:
            data = json.loads(SIGNAL_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Corrupt signal file, discarding: %s", exc)
            SIGNAL_FILE.unlink(missing_ok=True)
            return None
        
        # Deletion disabled for multi-terminal
        return data

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.route("/webhook", methods=["POST"])
def webhook() -> Any:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a valid JSON object."}), 400

    provided_token = (
        request.headers.get("X-TV-Token")
        or str(payload.get("token") or "")
    ).strip()

    if not provided_token or not _secure_compare(provided_token, WEBHOOK_SECRET):
        return jsonify({"error": "Unauthorized: invalid or missing token."}), 401

    signal = {k: v for k, v in payload.items() if k != "token"}
    if not signal:
        return jsonify({"error": "Signal payload is empty."}), 400

    try:
        _write_signal(signal)
    except OSError as exc:
        logger.error("Failed to persist signal: %s", exc)
        return jsonify({"error": "Failed to store signal."}), 500

    logger.info("Signal stored for EA pickup: %s", signal)

    # =========================================================================
    # TELEGRAM INTEGRATION (Reads exact SL and TP from TradingView JSON)
    # =========================================================================
    
    TELEGRAM_TOKEN = "8741194767:AAHyyDJowkozHi3szrBgVWh2hfiO0XtW5w0"  
    CHAT_ID = "-1003940784242"            

    if TELEGRAM_TOKEN != "YOUR_BOT_TOKEN":
        action_type = signal.get("action", "").upper()
        symbol_name = signal.get("symbol", "UNKNOWN")
        
        try:
            entry_price = float(signal.get("price", 0.0))
            # هنا التليجرام هيسحب الأرقام الذكية اللي محسوبة في TradingView
            sl_price = float(signal.get("sl", 0.0))
            tp_price = float(signal.get("tp", 0.0))
            lot_size = float(signal.get("lot", 0.04))
        except (ValueError, TypeError):
            entry_price = sl_price = tp_price = 0.0
            lot_size = 0.04

        if entry_price > 0:
            tg_message = (
                f"🚨 <b>New {action_type} Signal!</b> 🚨\n\n"
                f"💎 <b>Symbol:</b> {symbol_name}\n"
                f"📦 <b>Lot Size:</b> {lot_size}\n"
                f"🎯 <b>Entry Price:</b> {entry_price:.2f}\n"
                f"🛑 <b>Stop Loss:</b> {sl_price:.2f}\n"
                f"✅ <b>Take Profit:</b> {tp_price:.2f}\n\n"
                f"⚡ <i>Auto-executed on MT5</i>"
            )
        else:
            tg_message = f"🚨 <b>New {action_type} Signal!</b>\n💎 <b>Symbol:</b> {symbol_name}\n⚡ <i>Market Execution</i>"

        tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try:
            requests.post(tg_url, json={"chat_id": CHAT_ID, "text": tg_message, "parse_mode": "HTML"}, timeout=5)
        except Exception as e:
            logger.error("Failed to send Telegram message: %s", e)

    # =========================================================================

    return jsonify({"status": "ok", "stored": True}), 200


@app.route("/get_signal", methods=["GET"])
def get_signal() -> Any:
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
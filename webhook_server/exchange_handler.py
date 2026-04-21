"""
exchange_handler.py — Exchange Integration Module

Provides execute_trade() and the TradeError sentinel exception.
Switch from simulation mode to live trading by uncommenting the ccxt block
and supplying EXCHANGE_API_KEY / EXCHANGE_API_SECRET via Replit Secrets.
"""

import os
import re
import logging

logger = logging.getLogger("exchange_handler")

# ---------------------------------------------------------------------------
# Custom exception — lets main.py distinguish known trade failures from bugs
# ---------------------------------------------------------------------------

class TradeError(Exception):
    """Raised for known, recoverable exchange-side errors."""


# ---------------------------------------------------------------------------
# Optional: ccxt exchange setup
# ---------------------------------------------------------------------------
# Uncomment and configure to connect to a live or testnet exchange.
#
# import ccxt
#
# exchange = ccxt.binance({
#     "apiKey":  os.environ.get("EXCHANGE_API_KEY"),
#     "secret":  os.environ.get("EXCHANGE_API_SECRET"),
#     "options": {"defaultType": "future"},   # "spot" | "future" | "margin"
#     # Testnet — remove both 'urls' lines to trade on the live exchange:
#     "urls": {
#         "api": {
#             "public":  "https://testnet.binance.vision/api",
#             "private": "https://testnet.binance.vision/api",
#         }
#     },
# })


# ---------------------------------------------------------------------------
# Symbol normalisation
# ---------------------------------------------------------------------------

# Common quote currencies ordered longest-first so greedy matching works.
_KNOWN_QUOTES = [
    # Stablecoins (longest first to avoid partial matches)
    "USDT", "USDC", "BUSD", "TUSD", "FDUSD",
    # Crypto quote currencies
    "BTC", "ETH", "BNB",
    # Fiat currencies
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF",
]

_SLASH_RE = re.compile(r"^[A-Z0-9]+/[A-Z0-9]+$")


def _normalise_symbol(symbol: str) -> str:
    """
    Convert exchange-specific symbol strings to the universal CCXT slash format.

    Examples
    --------
    "BTCUSDT"   → "BTC/USDT"
    "ETHBTC"    → "ETH/BTC"
    "LINKUSDT"  → "LINK/USDT"
    "SOL/USDT"  → "SOL/USDT"   (already normalised — passed through)
    "DOGEBUSD"  → "DOGE/BUSD"
    """
    symbol = symbol.strip().upper()

    # Already in slash format
    if _SLASH_RE.match(symbol):
        return symbol

    # Try to split by known quote currency (longest match first)
    for quote in _KNOWN_QUOTES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            base = symbol[: -len(quote)]
            return f"{base}/{quote}"

    # Unknown quote currency — return as-is and let the exchange reject it
    logger.warning("Could not normalise symbol '%s'; passing through unchanged.", symbol)
    return symbol


# ---------------------------------------------------------------------------
# Main trade function
# ---------------------------------------------------------------------------

def execute_trade(action: str, symbol: str, price: str) -> dict:
    """
    Execute a trading signal received from TradingView.

    Parameters
    ----------
    action : str
        Direction of the trade — ``"buy"`` or ``"sell"`` (already normalised
        to lower-case by main.py).
    symbol : str
        Market symbol, e.g. ``"BTCUSDT"``, ``"BTC/USDT"``, ``"LINKUSDT"``.
    price : str
        Reference price string from TradingView (used for logging and limit
        orders). TradingView always sends numeric values as strings.

    Returns
    -------
    dict
        Structured result dict.  When live trading is active the ``order`` key
        contains the full CCXT order object returned by the exchange.

    Raises
    ------
    TradeError
        For known, recoverable errors (bad symbol, insufficient funds, etc.).
    Exception
        For unexpected infrastructure failures — re-raised so main.py can log
        and return HTTP 500.
    """
    logger.info(
        "execute_trade called — action=%s  symbol=%s  price=%s",
        action, symbol, price,
    )

    normalised = _normalise_symbol(symbol)

    # Validate price is numeric before any exchange call
    try:
        price_float = float(price)
    except (ValueError, TypeError) as exc:
        raise TradeError(f"Invalid price value '{price}': must be numeric.") from exc

    try:
        # ──────────────────────────────────────────────────────────────────────
        # SIMULATION MODE — replace this block with real CCXT calls when ready.
        # ──────────────────────────────────────────────────────────────────────
        logger.info(
            "Simulating %s order — symbol: %s  price: %s",
            action.upper(), normalised, price,
        )

        simulated_order = {
            "id":     "SIM-000001",
            "symbol": normalised,
            "side":   action,
            "type":   "market",
            "price":  price_float,
            "amount": 0.001,
            "status": "simulated",
        }

        logger.info("Simulated order: %s", simulated_order)
        return {"status": "simulated", "order": simulated_order}

        # ──────────────────────────────────────────────────────────────────────
        # LIVE MODE — uncomment after configuring ccxt at the top of this file.
        # ──────────────────────────────────────────────────────────────────────
        # order = exchange.create_order(
        #     symbol=normalised,
        #     type="market",
        #     side=action,
        #     amount=float(os.environ.get("TRADE_AMOUNT", "0.001")),
        # )
        # return {"status": "filled", "order": order}

    except TradeError:
        raise  # Already structured — let main.py handle it

    except Exception as exc:
        logger.error(
            "execute_trade FAILED — action=%s  symbol=%s  error=%s",
            action, normalised, exc,
            exc_info=True,
        )
        raise

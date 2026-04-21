"""
exchange_handler.py — Exchange Integration Module

Provides the execute_trade() function that will be wired to a real CCXT-based
exchange (e.g. Binance, Bybit, OKX) once you supply API credentials.

All actual exchange communication will happen here, keeping main.py clean and
focused solely on HTTP request handling.
"""

import logging

# Module-level logger — inherits the root configuration set in main.py.
logger = logging.getLogger("exchange_handler")

# ---------------------------------------------------------------------------
# Optional: import ccxt when real trading is enabled
# ---------------------------------------------------------------------------
# Uncomment the lines below and fill in your API credentials (via environment
# variables) to connect to a live or paper-trading exchange.
#
# import os
# import ccxt
#
# exchange = ccxt.binance({
#     "apiKey":  os.environ.get("EXCHANGE_API_KEY"),
#     "secret":  os.environ.get("EXCHANGE_API_SECRET"),
#     "options": {"defaultType": "future"},   # "spot" | "future" | "margin"
#     # Remove the next two lines to trade on the LIVE exchange:
#     "urls": {"api": {"public":  "https://testnet.binance.vision/api",
#                      "private": "https://testnet.binance.vision/api"}},
# })


def execute_trade(action: str, symbol: str, price: str) -> dict:
    """
    Execute a trading signal received from TradingView.

    Parameters
    ----------
    action : str
        Direction of the trade — ``"buy"`` or ``"sell"``.
    symbol : str
        Market symbol in CCXT format, e.g. ``"BTC/USDT"`` or ``"BTCUSDT"``.
    price : str
        Reference price from the TradingView alert (used for logging / limit
        orders).  Passed as a string because TradingView always sends strings.

    Returns
    -------
    dict
        A structured result dictionary describing the outcome of the attempt.
        When live trading is enabled the ``order`` key will contain the full
        CCXT order object returned by the exchange.

    Notes
    -----
    The function currently runs in **placeholder / simulation mode**.
    Replace the body of the ``try`` block below with real CCXT calls once you
    are ready to go live.

    Example live market order (uncomment after setting up ccxt above):

        order = exchange.create_order(
            symbol=symbol,
            type="market",
            side=action,          # "buy" | "sell"
            amount=0.001,         # quantity — read from env / config in prod
        )
        return {"status": "filled", "order": order}
    """

    logger.info(
        "execute_trade called — action=%s  symbol=%s  price=%s",
        action,
        symbol,
        price,
    )

    try:
        # ------------------------------------------------------------------
        # PLACEHOLDER — replace with real CCXT order logic
        # ------------------------------------------------------------------
        # Normalise the symbol to the CCXT slash format if needed
        normalised_symbol = symbol if "/" in symbol else f"{symbol[:3]}/{symbol[3:]}"

        logger.info(
            "Simulating %s order for %s at reference price %s",
            action.upper(),
            normalised_symbol,
            price,
        )

        # Simulated response matching the shape of a real CCXT order object
        simulated_order = {
            "id": "SIM-000001",
            "symbol": normalised_symbol,
            "side": action,
            "type": "market",
            "price": float(price),
            "amount": 0.001,          # placeholder quantity
            "status": "simulated",
        }

        logger.info("Simulated order created: %s", simulated_order)
        return {"status": "simulated", "order": simulated_order}

    except Exception as exc:
        # Log the full exception and propagate a structured error upward so
        # main.py can return a meaningful HTTP 500 response if needed.
        logger.error(
            "execute_trade FAILED — action=%s  symbol=%s  error=%s",
            action,
            symbol,
            str(exc),
            exc_info=True,
        )
        raise

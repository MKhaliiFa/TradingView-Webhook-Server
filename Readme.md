# TradingView Webhook Server

## Overview

A production-ready Python 3.11 Flask server that receives automated crypto trading signals
from TradingView alerts and routes them to an exchange via CCXT.

**This is a pure Python project.** No Node.js, no pnpm, no build step.
The dashboard is rendered server-side with Jinja2 + Bootstrap CDN.

---

## File Structure

```
webhook_server/
├── main.py              # Flask app — all routes, auth, logging, BufferHandler
├── exchange_handler.py  # execute_trade(), TradeError, symbol normalisation
├── requirements.txt     # Flask 3.1.1 · ccxt 4.4.71 · python-dotenv 1.1.0
└── templates/
    └── dashboard.html   # Bootstrap 5.3 dark dashboard (Jinja2, no build step)

scripts/
└── post-merge.sh        # Post-merge hook: pip install -r requirements.txt

artifacts/api-server/
└── .replit-artifact/artifact.toml   # Production: python webhook_server/main.py
```

---

## Endpoints

| Method | Path         | Auth | Description                                             |
|--------|--------------|------|---------------------------------------------------------|
| GET    | `/`          | none | Bootstrap dashboard — status, live logs, connection guide |
| GET    | `/favicon.ico`| none | Inline SVG favicon (suppresses 404 noise)               |
| GET    | `/health`    | none | Liveness probe → `{status, start_time, uptime}`        |
| GET    | `/logs`      | none | JSON log stream, polled by dashboard every 2 s          |
| POST   | `/webhook`   | token| Receive TradingView alert JSON → execute trade          |

---

## Webhook Payload

```json
{
  "token":  "YOUR_WEBHOOK_SECRET",
  "action": "buy",
  "symbol": "BTCUSDT",
  "price":  "65000"
}
```

- `action` must be `"buy"` or `"sell"` (for Indicator alerts: hardcode the value)
- Token may alternatively be sent as `X-TV-Token` HTTP header (header takes priority)
- All fields are required; missing fields → HTTP 400

---

## Authentication

Supplied token is compared to `WEBHOOK_SECRET` env var using `hmac.compare_digest` (timing-safe).

---

## Secrets (Replit Secrets)

| Name            | Purpose                          |
|-----------------|----------------------------------|
| `WEBHOOK_SECRET`| Required — shared token with TradingView |
| `SESSION_SECRET`| Reserved for future session use  |

---

## Development Workflows

| Workflow | Command | Port |
|---|---|---|
| TradingView Webhook Server (run button) | `cd webhook_server && PORT=5000 python main.py` | 5000 |
| artifacts/api-server: Webhook Server (preview) | `cd webhook_server && PORT=8080 python main.py` | 8080 |

---

## Production Deployment

Production run command in `artifact.toml`:
```
python webhook_server/main.py
```
`PORT=8080` is set via env. **No build step** — Flask starts directly, bypasses all Node.js overhead.
Health check: `GET /health`

---

## Symbol Normalisation

`exchange_handler.py` converts TradingView symbols → ccxt slash format:

| Input      | Output      |
|------------|-------------|
| `BTCUSDT`  | `BTC/USDT`  |
| `LINKUSDT` | `LINK/USDT` |
| `ETHBTC`   | `ETH/BTC`   |
| `BTC/USDT` | `BTC/USDT`  |

Quote currencies (longest-first): USDT, USDC, BUSD, TUSD, FDUSD, BTC, ETH, BNB.

---

## Going Live (Exchange Integration)

To switch from simulation to live trading:

1. Add `EXCHANGE_API_KEY` and `EXCHANGE_API_SECRET` to Replit Secrets
2. Uncomment the ccxt exchange block in `exchange_handler.py`
3. Replace the simulation block with `exchange.create_order(...)`
4. Optionally set `TRADE_AMOUNT` secret for position sizing

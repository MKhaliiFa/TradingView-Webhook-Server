# Workspace

## Overview

Python 3.11 Flask webhook server for receiving automated crypto trading signals from TradingView.
The project also contains a pnpm workspace scaffold (legacy artifact registration), but **all runtime logic is pure Python** — no Node.js build step is involved in development or production.

## Architecture

```
webhook_server/
├── main.py              # Flask app — all routes, logging, BufferHandler
├── exchange_handler.py  # execute_trade(), TradeError, symbol normalisation (ccxt-ready)
├── requirements.txt     # Flask 3.1.1 · ccxt 4.4.71 · python-dotenv 1.1.0
└── templates/
    └── dashboard.html   # Bootstrap 5.3 dark dashboard (Jinja2, no build step)
```

## Endpoints

| Method | Path         | Description                                           |
|--------|--------------|-------------------------------------------------------|
| GET    | `/`          | Bootstrap dashboard — server status, live logs, guide |
| GET    | `/health`    | Liveness probe → `{status, start_time, uptime}`       |
| GET    | `/logs`      | JSON log stream (polled by dashboard every 2 s)        |
| POST   | `/webhook`   | Receive TradingView alert JSON                        |

### Webhook payload

```json
{
  "token":  "YOUR_WEBHOOK_SECRET",   // or pass via X-TV-Token header
  "action": "buy|sell",
  "symbol": "BTCUSDT",
  "price":  "50000"
}
```

## Authentication

Token is compared with `WEBHOOK_SECRET` env var using `hmac.compare_digest` (timing-safe).
Supply via `X-TV-Token` header **or** `"token"` field in the JSON body.

## Secrets

- `WEBHOOK_SECRET` — set in Replit Secrets (never in code)
- `SESSION_SECRET` — reserved for future session use

## Workflows (dev)

| Workflow | Command | Port |
|---|---|---|
| TradingView Webhook Server (run button) | `cd webhook_server && PORT=5000 python main.py` | 5000 |
| artifacts/api-server: Webhook Server (preview pane) | `cd /home/runner/workspace/webhook_server && PORT=8080 python main.py` | 8080 |

Both run Flask; the artifact workflow (port 8080) powers the preview pane (port 80 externally).

## Production (deployment)

Production run command in `artifact.toml`:
```
python webhook_server/main.py
```
With `PORT=8080`. **No build step** — Flask starts directly, bypassing all Node.js/pnpm overhead.
Health check: `GET /health`

## Symbol Normalisation

`exchange_handler.py` converts TradingView symbols → ccxt format:
- `BTCUSDT` → `BTC/USDT`
- `LINKUSDT` → `LINK/USDT`  (handles 4-letter base symbols)

Quote currencies checked (longest-first): USDT, USDC, BUSD, TUSD, BTC, ETH, BNB, USD, EUR.

## Exchange Integration

`execute_trade()` is a structured placeholder. To go live:
1. Add exchange credentials as Replit Secrets
2. Uncomment the ccxt exchange initialisation in `exchange_handler.py`
3. Replace the simulation block with a real `exchange.create_order()` call

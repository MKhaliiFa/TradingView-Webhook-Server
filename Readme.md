<div align="center">

# TradingView → MT5 Bridge

**A lightweight Flask micro-service that turns TradingView alerts into live MetaTrader 5 trades — with instant Telegram notifications.**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1.1-000000?style=for-the-badge&logo=flask&logoColor=white)
![Gunicorn](https://img.shields.io/badge/Gunicorn-23.0-499848?style=for-the-badge&logo=gunicorn&logoColor=white)
![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)

</div>

---

## Overview

This service sits between **TradingView** and your **MT5 Expert Advisor**, acting as an authenticated relay. When TradingView fires an alert, the webhook validates it, persists the signal to disk, and simultaneously pushes a formatted message to your Telegram channel — so your EA can pick it up and you stay in the loop in real time.

> Designed for **zero-config cloud deployment** on Render, Railway, Fly.io, or any WSGI host.

---

## Features

- **Signed webhooks** using timing-safe HMAC comparison (`hmac.compare_digest`).
- **Thread-safe** signal storage with atomic file writes.
- **Multi-terminal friendly** — the signal file is not deleted after reads, so multiple MT5 instances can consume the same alert.
- **Telegram notifications** with auto-calculated SL / TP levels for Gold (XAUUSD).
- **Minimal surface area** — a single `main.py`, no build step, no frontend.
- **Production ready** — ships with Gunicorn for concurrent request handling.

---

## Architecture

```
┌──────────────┐      POST /webhook      ┌──────────────┐
│  TradingView │ ─────────────────────▶  │   Flask App  │
│    Alert     │       (+ token)         │  (main.py)   │
└──────────────┘                         └──────┬───────┘
                                                │
                              ┌─────────────────┼─────────────────┐
                              ▼                 ▼                 ▼
                       ┌────────────┐    ┌────────────┐    ┌────────────┐
                       │ signal.json│    │  Telegram  │    │   Logs     │
                       │   (disk)   │    │    Bot     │    │  (stdout)  │
                       └─────┬──────┘    └────────────┘    └────────────┘
                             │
                      GET /get_signal
                             │
                             ▼
                      ┌────────────┐
                      │  MT5  EA   │
                      └────────────┘
```

---

## API Reference

### `POST /webhook`

Receives a TradingView alert, authenticates it, and persists the signal.

**Headers**

| Name           | Required | Description                            |
| -------------- | -------- | -------------------------------------- |
| `X-TV-Token`   | optional | Shared secret (overrides body `token`) |
| `Content-Type` | yes      | `application/json`                     |

**Body**

```json
{
  "token": "YOUR_WEBHOOK_SECRET",
  "action": "BUY",
  "symbol": "XAUUSD",
  "price": "2350.50"
}
```

**Responses**

| Status | Meaning                        |
| ------ | ------------------------------ |
| `200`  | Signal stored, Telegram sent   |
| `400`  | Malformed or empty payload     |
| `401`  | Invalid or missing token       |
| `500`  | Failed to write signal to disk |

---

### `GET /get_signal`

Polled by the MT5 EA. Returns the most recent stored signal without deleting it.

```json
{
  "status": "ok",
  "signal": {
    "action": "BUY",
    "symbol": "XAUUSD",
    "price": "2350.50"
  }
}
```

When no signal is pending, responds with `{ "status": "empty", "signal": null }`.

---

## Configuration

All runtime configuration is done via **environment variables**:

| Variable         | Required | Default         | Description                                |
| ---------------- | -------- | --------------- | ------------------------------------------ |
| `WEBHOOK_SECRET` | yes      | —               | Shared secret TradingView sends in payload |
| `SIGNAL_FILE`    | no       | `./signal.json` | Path where the current signal is stored    |
| `PORT`           | no       | `8080`          | HTTP port the service binds to             |
| `TELEGRAM_TOKEN` | no       | —               | Bot token for Telegram notifications       |
| `TELEGRAM_CHAT`  | no       | —               | Target chat / channel ID                   |

> **Security note:** the repository currently embeds a default Telegram token for convenience. For production, move it to an env var and revoke the committed one.

---

## Quick Start

### Local development

```bash
# 1. Clone
git clone https://github.com/<your-user>/TradingView-Listener-2.git
cd TradingView-Listener-2

# 2. Install
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Run
export WEBHOOK_SECRET="super-secret-value"
python main.py
```

The server starts on `http://localhost:8080`.

### Smoke test

```bash
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -H "X-TV-Token: super-secret-value" \
  -d '{"action":"BUY","symbol":"XAUUSD","price":"2350.50"}'
```

Expected response:

```json
{ "status": "ok", "stored": true }
```

---

## Deployment (Render)

1. Create a new **Web Service** and point it at this repository.
2. Use the following settings:

| Setting       | Value                                     |
| ------------- | ----------------------------------------- |
| Environment   | Python 3.11                               |
| Build Command | `pip install -r requirements.txt`         |
| Start Command | `gunicorn -w 2 -b 0.0.0.0:$PORT main:app` |

3. Add `WEBHOOK_SECRET` (and Telegram vars) under **Environment → Secret Files**.
4. Point the TradingView alert webhook URL to `https://<your-service>.onrender.com/webhook`.

---

## TradingView Alert Template

Paste this into the alert **message** field:

```json
{
  "token": "YOUR_WEBHOOK_SECRET",
  "action": "{{strategy.order.action}}",
  "symbol": "{{ticker}}",
  "price": "{{close}}"
}
```

---

## Project Structure

```
TradingView-Listener-2/
├── main.py             # Flask app — webhook, signal store, Telegram push
├── requirements.txt    # Flask · gunicorn · requests
├── pyproject.toml      # Project metadata
├── Readme.md           # You are here
└── signal.json         # Generated at runtime (gitignored)
```

---

## Roadmap

- [ ] Move Telegram credentials fully to environment variables
- [ ] Pluggable SL / TP rules per symbol (instead of hard-coded Gold values)
- [ ] Redis / SQLite backend as an alternative to file storage
- [ ] Per-request rate limiting
- [ ] Docker image with multi-stage build

---

## License

Released under the **MIT License**. See `LICENSE` for details.

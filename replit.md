# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.

## TradingView Webhook Server (`webhook_server/`)

A standalone Python 3.11 Flask server for receiving automated crypto trading signals from TradingView.

- **Entry point**: `webhook_server/main.py` — runs on port 5000
- **Exchange logic**: `webhook_server/exchange_handler.py` — placeholder with CCXT structure
- **Dependencies**: `webhook_server/requirements.txt` (Flask, ccxt, python-dotenv)
- **Workflow**: "TradingView Webhook Server" (`python main.py`)
- **Secret**: `WEBHOOK_SECRET` env var (set in Replit Secrets)
- **Auth**: token supplied via `X-TV-Token` header or `"token"` JSON field
- **Endpoints**:
  - `GET /health` — liveness probe
  - `POST /webhook` — receives TradingView alert JSON `{action, symbol, price}`

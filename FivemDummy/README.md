# FiveM Dummy Server (Node.js)

This project simulates a FiveM game server that securely executes both monetization transactions and admin actions from a central backend API.

## Features

- Express server with health endpoint
- Polling loop every 5 seconds (configurable)
- Backend authentication using `Authorization: Bearer API_KEY`
- **Player state push** — after each poll cycle, the current simulated player
  list is pushed to `POST /api/v1/service/fivem/players` so the admin dashboard
  shows an up-to-date "Online Players" panel.
- Monetization flow:
	- `GET /api/sync/updates`
	- Simulated money/item rewards
	- `POST /api/confirm-transaction`
- Admin control flow:
	- `GET /api/sync/updates`
	- Simulated `ban`, `kick`, `give_role`, `remove_role`
	- `POST /api/confirm-admin-action` — called by FivemDummy immediately after
	  executing each action (the Discord bot does the same for Discord-originated
	  actions; confirm is idempotent so both calling it is safe).
- One-shot admin simulation flags:
	- `--simulate-rewards` -> `POST /api/admin/simulate-fivem-rewards`
	- `--simulate-actions` -> `POST /api/admin/simulate-fivem-actions`
	- `--simulate-all` -> both calls
- In-memory player database for simulation
- Basic payload validation before execution
- Retry handling with backoff and jitter
- Logging to both console and file

## Project Structure

- `server.js` - main app, polling scheduler, secure endpoints
- `config/env.js` - environment loader and required settings
- `services/apiClient.js` - authenticated backend API calls
- `services/playerManager.js` - in-memory player state and action handlers
- `utils/logger.js` - console + file logger
- `utils/retry.js` - retry utility for transient failures

## Setup

1. Copy `.env.example` to `.env`
2. Set `SILVERSHADE_API` and `SILVERSHADE_API_KEY`
3. Optionally set `SILVERSHADE_ADMIN_TOKEN` for simulation CLI flags
4. Install dependencies:
	 - `npm.cmd install`
5. Run the server:
	 - `npm.cmd start`

## CLI Simulation Modes

- `node server.js --simulate-rewards`
- `node server.js --simulate-actions`
- `node server.js --simulate-all`

When any simulate flag is used, `SILVERSHADE_ADMIN_TOKEN` is required and the script exits after the one-shot admin test call(s).

## Test Endpoints

- `GET /health` (no auth)
- `GET /players` (requires API key header)

For `/players`, include:

`Authorization: Bearer YOUR_BACKEND_API_KEY`

## Real FiveM Mapping Notes

- Transaction reward application in `services/playerManager.js` is where you would call ESX/QBCore economy and inventory APIs in production.
- Admin action handlers are where you would map to real FiveM player identifiers, permission systems, and server events (`DropPlayer`, ban systems, role/group resources).
- The polling + confirmation pattern is kept separate from game framework calls so the simulation can be swapped out with live FiveM logic later.

## URL Normalization

`SILVERSHADE_API` accepts either style and is normalized internally:

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/api`

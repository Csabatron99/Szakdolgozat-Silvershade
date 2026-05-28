# SilverShade

Central backend system for FiveM server monetization and Discord moderation management.
Built as a university thesis project demonstrating REST API design, secure authentication,
and payment integration from scratch.

---

## Architecture (Option B — Separated API + Frontend)

```
ProgramThesis/
├── API/          ← Pure FastAPI REST API (JSON only, port 8000)
├── Website/      ← Frontend server: HTML/CSS/JS + reverse proxy to API (port 8080)
├── DiscordBot/   ← Node.js Discord bot — polls API, mirrors events to Discord
└── FivemDummy/   ← Node.js dummy FiveM server — polls API, simulates in-game delivery
```

### How it works

```
[Browser / User]
      │
      ▼ port 8080
┌─────────────────────┐
│   Website/serve.py  │  ← Static HTML + reverse proxy
│   (FastAPI)         │
└─────────┬───────────┘
          │ /api/* forwarded
          ▼ port 8000
┌─────────────────────┐
│   API/main.py       │  ← Pure REST API
│   (FastAPI + Mongo) │
└─────────────────────┘
      ▲           ▲
      │           │
      │           │  Bearer API Key
      │    ┌──────┴────────────┐
      │    │  FivemDummy       │  polls /api/sync/updates every 5s
      │    │  (Node.js)        │  confirms transactions and admin actions
      │    └───────────────────┘
      │
      │    ┌───────────────────┐
      └────│  DiscordBot       │  polls /api/sync/updates every 5s
           │  (Node.js)        │  mirrors events to Discord channels
           └───────────────────┘
```

### Full purchase-to-delivery flow

1. User logs in at `http://localhost:8080/auth`
2. User buys a store item → transaction queued as `pending` in MongoDB
3. FivemDummy polls `/api/sync/updates` every 5 seconds, picks up the transaction
4. FivemDummy applies the reward to the in-memory player list
5. FivemDummy calls `POST /api/confirm-transaction` → status becomes `completed`
6. Admin can also click **Simulate FiveM Pickup** on the admin dashboard to skip step 3-4

---

## Quick Start

### 1 — API server

```bash
cd API
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # then edit .env with real secrets
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Swagger docs: http://127.0.0.1:8000/docs

### 2 — Frontend (Website)

```bash
cd Website
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # set SILVERSHADE_API=http://127.0.0.1:8000
uvicorn serve:app --reload --host 127.0.0.1 --port 8080
```

Open: http://localhost:8080

### 3 — FiveM Dummy

```bash
cd FivemDummy
npm.cmd install
copy .env.example .env          # set SILVERSHADE_API and SILVERSHADE_API_KEY
npm.cmd start
```

### 4 — Discord Bot

```bash
cd DiscordBot
npm.cmd install
copy .env.example .env          # set DISCORD_TOKEN, SILVERSHADE_API, SILVERSHADE_API_KEY
npm.cmd start
```

---

## Environment Variable Reference

### API/.env

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | JWT signing secret — min 32 characters random string |
| `SERVICE_API_KEY` | Yes | Bearer token used by FivemDummy and DiscordBot |
| `MONGODB_URI` | Yes | MongoDB connection string |
| `MONGODB_DB` | Yes | Database name (default: `silvershade`) |
| `ALLOWED_ORIGINS` | Yes | Comma-separated CORS origins (e.g. `http://localhost:8080`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | JWT expiry in minutes (default: 120) |
| `AUTH_COOKIE_SECURE` | No | Set `True` in production HTTPS (default: False) |
| `DISCORD_TEST_WEBHOOK_URL` | No | Discord webhook URL for admin simulate endpoint |
| `RATE_LIMIT_REQUESTS` | No | Max requests per IP per window (default: 100) |
| `RATE_LIMIT_WINDOW_SECONDS` | No | Rate limit window in seconds (default: 60) |

### Website/.env

| Variable | Required | Description |
|---|---|---|
| `SILVERSHADE_API` | Yes | URL of the API server (default: `http://127.0.0.1:8000`) |
| `PORT` | No | Port for this server (default: 8080) |

### FivemDummy/.env

| Variable | Required | Description |
|---|---|---|
| `SILVERSHADE_API` | Yes | URL of the API server |
| `SILVERSHADE_API_KEY` | Yes | Same value as API's `SERVICE_API_KEY` |
| `SILVERSHADE_ADMIN_TOKEN` | Only for `--simulate-*` flags | Admin JWT for one-shot simulation runs |
| `PORT` | No | Port for the dummy server (default: 3000) |
| `POLL_INTERVAL_MS` | No | Polling interval in ms (default: 5000) |

### DiscordBot/.env

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | Yes | Bot token from Discord Developer Portal |
| `DISCORD_CLIENT_ID` | Yes | Application client ID |
| `DISCORD_GUILD_ID` | Yes | Your Discord server ID |
| `SILVERSHADE_API` | Yes | URL of the API server |
| `SILVERSHADE_API_KEY` | Yes | Same value as API's `SERVICE_API_KEY` |
| `SILVERSHADE_ADMIN_TOKEN` | Only for `--simulate-discord-pickup` | Admin JWT |
| `LOG_CHANNEL_IDS` | Yes | Comma-separated Discord channel IDs for event logs |
| `ADMIN_ROLE_NAME` | No | Discord role name for admin commands (default: `Admin`) |

---

## Generate Secure Secrets

```bash
# SECRET_KEY (Python):
python -c "import secrets; print(secrets.token_hex(32))"

# SERVICE_API_KEY (Python):
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Task List

See [TASKS.md](TASKS.md) for the full list of completed and pending work.

# Discord Admin Bridge Bot

Node.js + discord.js bot that acts as an administration bridge between Discord, a website backend API, and your game server.

## Features

- Command system with `!` prefix (configurable)
- Secure API integration with `axios` and `Authorization: Bearer API_KEY`
- Admin-role guard for sensitive commands
- Polling-based event sync from backend to Discord log channels
- Discord role management and backend role synchronization
- Basic logging and centralized configuration

## Project Structure

- `index.js` - bot bootstrap, command handling, permission checks, polling loop
- `commands/` - command handlers
- `services/apiClient.js` - backend API adapter
- `services/discordManager.js` - Discord logging + role sync operations
- `services/logger.js` - simple logger
- `config/index.js` - environment parsing and validation

## Commands

- `!ping` -> test bot
- `!user <userId?>` -> fetch user data from API (defaults to your Discord ID)
- `!ban <userId> [reason]` -> admin only, send ban request to API
- `!kick <userId> [reason]` -> admin only, send kick request to API
- `!give-money <userId> <amount> [note]` -> admin only, create transaction via API
- `!role <userId> <roleName> [add|remove]` -> admin only, update role via API + Discord role change
- `!transactions [limit]` -> admin only, list recent transactions

## Setup

1. Install dependencies:

```bash
npm install
```

2. Create `.env` from `.env.example` and fill in real values.

3. Start the bot:

```bash
npm start
```

## Backend API Expectations

The bot expects these API routes (you can adjust in `services/apiClient.js`):

- `GET /users/:id`
- `POST /admin/ban`
- `POST /admin/kick`
- `POST /transactions`
- `GET /transactions/recent?limit=5`
- `POST /roles/assign`
- `GET /sync/updates?cursor=...`
- `POST /discord/roles/sync`

### Suggested `/sync/updates` response

```json
{
  "cursor": "opaque_cursor_token",
  "transactions": [
    { "id": "tx_1", "userId": "123", "type": "credit", "amount": 1000, "createdAt": "2026-03-22T12:00:00Z" }
  ],
  "adminActions": [
    { "type": "ban", "userId": "123" },
    { "type": "give_money", "userId": "124", "amount": 1000 }
  ],
  "roleUpdates": [
    { "userId": "123", "roles": ["admin", "vip"] }
  ]
}
```

## Security Notes

- Keep `.env` private and never commit it.
- API key is only read from environment variables.
- Command arguments are validated before API calls.
- API errors are sanitized to avoid leaking internal details.

## Integration Notes

- Website/admin panel can write moderation and transaction events into backend queues.
- Game server can publish player-state events (transactions, punishments, role changes) to backend.
- Bot polling reads those updates and mirrors them to Discord logs and role state.

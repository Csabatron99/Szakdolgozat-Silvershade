# SilverShade - FastAPI Control Center

SilverShade is a secure central control system for FiveM and Discord integrations.
It provides:

- User and admin authentication with JWT
- API key protected machine-to-machine endpoints (FiveM/Discord bot)
- Pending transaction workflow and reward confirmation
- Pending admin action workflow and execution confirmation
- Dark modern admin dashboard built with Jinja2 + Bootstrap

## Tech Stack

- FastAPI + Uvicorn
- MongoDB (Motor/PyMongo)
- JWT (`python-jose`)
- Password hashing (`passlib` + `bcrypt`)
- Jinja2 templates + custom SilverShade CSS

## Project Structure

- `main.py`
- `app/routers/` (`auth.py`, `users.py`, `transactions.py`, `admin_actions.py`, `web.py`)
- `app/services/` (security, dependencies, serializers)
- `app/middleware/` (logging, rate limiting)
- `app/database/` (Mongo init)
- `app/schemas/` (Pydantic models)
- `templates/` (landing/auth/user/admin pages)
- `static/` (CSS/JS)

## Setup

1. Create virtual environment and install dependencies:
   - `pip install -r requirements.txt`
2. Create `.env` from `.env.example` and update values.
3. Ensure MongoDB is running.
4. Run the app:
   - `uvicorn main:app --reload`

## Core Endpoints

### Auth
- `POST /api/auth/register`
- `POST /api/auth/login`

### Admin/User
- `GET /api/users` (admin)
- `POST /api/users/update-balance` (admin)

### Store/Transactions
- `POST /api/store/items` (admin)
- `GET /api/store/items` (user/admin)
- `POST /api/store/buy` (user/admin)
- `GET /api/transactions` (user/admin)
- `GET /api/pending-transactions` (API key)
- `POST /api/confirm-transaction` (API key)

### Admin Actions
- `POST /api/create-admin-action` (admin)
- `GET /api/admin-actions` (API key)
- `POST /api/confirm-admin-action` (API key)

## API Key Usage

For game server or Discord bot calls, include header:

`Authorization: Bearer <SERVICE_API_KEY>`

## Security Notes

- Never expose `SERVICE_API_KEY` in frontend code.
- JWT protects user/admin routes.
- API key protects server-to-server routes.
- Admin-only operations enforce role checks.
- Logging middleware records every request.
- Rate limiting middleware helps reduce abuse.

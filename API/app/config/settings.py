from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SilverShade API"
    secret_key: str = "change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    auth_cookie_name: str = "silvershade_access_token"
    # Set True in production (HTTPS only). Override in .env for local dev.
    auth_cookie_secure: bool = False

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "silvershade"

    service_api_key: str = "change-this-service-api-key"
    discord_test_webhook_url: str = ""
    # Optional secret for HMAC-SHA256 signing of outbound webhook calls (§1.7).
    # If empty, the signature header is omitted (still sends webhook).
    webhook_secret: str = ""

    # Comma-separated list of allowed CORS origins.
    # Example: http://localhost:8080,https://yourdomain.com
    allowed_origins: str = "http://localhost:8080,http://127.0.0.1:8080"

    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # Optional Redis URL for distributed rate limiting.
    # If empty, rate limiting uses an in-process dict (fine for single-instance deployments).
    # Example: redis://localhost:6379/0
    redis_url: str = ""

    # ── Stripe Payment Integration (§3) ──────────────────────────────────────
    # Leave as empty strings until Stripe integration is implemented.
    # Sign up at stripe.com (free test mode available).
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # Base URL of the frontend (Website) server — used for Stripe redirect URLs.
    # Must NOT have a trailing slash.
    frontend_url: str = "http://localhost:8080"


settings = Settings()

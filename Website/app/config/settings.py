from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SilverShade Control"
    secret_key: str = "change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    auth_cookie_name: str = "silvershade_access_token"
    auth_cookie_secure: bool = False

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "silvershade"

    service_api_key: str = "change-this-service-api-key"
    discord_test_webhook_url: str = ""

    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60


settings = Settings()

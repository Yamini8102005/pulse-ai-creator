from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./pulse.db"
    breeth_api_key: str = ""
    breeth_base_url: str = "https://api.thebreeth.com"
    publish_interval_minutes: float = 120.0
    scheduler_poll_seconds: int = 10
    scheduler_claim_stale_minutes: int = 1
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

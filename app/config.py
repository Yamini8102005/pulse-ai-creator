from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./pulse.db"
    breeth_api_key: str = ""
    breeth_base_url: str = "https://api.thebreeth.com"
    publish_interval_minutes: float = 120.0
    scheduler_poll_seconds: int = 10
    scheduler_claim_stale_minutes: int = 1
    llm_provider: str = "gemini"
    llm_api_key: str = ""
    llm_api_base: str = ""
    llm_model: str = ""
    gemini_api_key: str = ""
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1"
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    frontend_origin: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

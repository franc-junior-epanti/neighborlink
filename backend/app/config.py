from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NeighborLink API"
    environment: str = "development"
    api_version: str = "0.1.0"
    database_url: str = "postgresql+psycopg://neighborlink:neighborlink@localhost:55432/neighborlink"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NeighborLink API"
    environment: str = "development"
    api_version: str = "0.1.0"
    database_url: str = "postgresql+psycopg://neighborlink:neighborlink@localhost:55432/neighborlink"
    aws_region: str = "eu-west-1"
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    auth_mode: str = "cognito"
    frontend_origin: str = "http://localhost:5173"
    agent_runtime_mode: str = "local"
    agent_runtime_arn: str = ""
    agent_runtime_qualifier: str = "DEFAULT"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()

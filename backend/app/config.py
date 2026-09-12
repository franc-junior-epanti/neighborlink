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
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    gmail_sender_email: str = ""
    infobip_base_url: str = ""
    infobip_api_key: str = ""
    infobip_whatsapp_sender: str = ""
    response_signing_secret: str = "dev-insecure-secret-change-me"
    public_api_base_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()

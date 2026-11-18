"""Configuración leída de variables de entorno (o de un archivo .env en desarrollo)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/employer_buddy"

    # WhatsApp Cloud API (Meta)
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_api_base: str = "https://graph.facebook.com"
    whatsapp_api_version: str = "v21.0"

    # Números autorizados, separados por comas, en formato internacional sin "+".
    allowed_numbers: str = ""

    # Claude API
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: str = "medium"

    worker_poll_seconds: float = 1.0

    @property
    def allowed_number_set(self) -> set[str]:
        return {n.strip().lstrip("+") for n in self.allowed_numbers.split(",") if n.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()

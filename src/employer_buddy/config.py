"""Configuración leída de variables de entorno (o de un archivo .env en desarrollo)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "solo-para-desarrollo"


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

    # Página de revisión del perfil
    public_base_url: str = "http://localhost:8000"
    session_secret: str = DEV_SECRET
    review_link_hours: int = 24
    review_session_hours: int = 2

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    def check(self) -> None:
        """Evita arrancar fuera de desarrollo con el secreto de ejemplo."""
        if not self.is_development and self.session_secret == DEV_SECRET:
            raise RuntimeError("Configura SESSION_SECRET antes de arrancar fuera de desarrollo.")

    @property
    def allowed_number_set(self) -> set[str]:
        return {n.strip().lstrip("+") for n in self.allowed_numbers.split(",") if n.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()

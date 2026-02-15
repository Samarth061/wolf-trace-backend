"""Pydantic Settings loaded from environment."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    backboard_api_key: str = ""
    neo4j_uri: str = ""
    neo4j_username: str = ""
    neo4j_password: str = ""
    factcheck_api_key: str = ""  # Falls back to gemini_api_key if unset (Fact Check Tools API)
    twelvelabs_api_key: str = ""
    twelvelabs_index_id: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    media_base_url: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

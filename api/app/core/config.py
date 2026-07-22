from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "longhaul-api"
    environment: str = Field(default="dev")

    postgres_host: str = Field(default="postgres")
    postgres_port: int = Field(default=5438)
    postgres_db: str = Field(default="longhaul")
    postgres_user: str = Field(default="longhaul")
    postgres_password: str = Field(default="longhaul")

    redis_host: str = Field(default="redis")
    redis_port: int = Field(default=6438)

    minio_endpoint: str = Field(default="minio:9018")
    minio_access_key: str = Field(default="longhaul")
    minio_secret_key: str = Field(default="longhaul")

    smtp_host: str = Field(default="mailpit")
    smtp_port: int = Field(default=1038)

    # F9 AI gateway — real Claude provider activates when a key is present; empty
    # -> the deterministic FakeModelProvider (canned output). Key lives in .env only.
    anthropic_api_key: str = Field(default="")
    f9_model: str = Field(default="claude-haiku-4-5-20251001")

    # F1 authority verification — real FMCSA QCMobile lookup activates when a webKey
    # is present; empty -> the deterministic FakeAuthorityVerifier. Key in .env only.
    fmcsa_webkey: str = Field(default="")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

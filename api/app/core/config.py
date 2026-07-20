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

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

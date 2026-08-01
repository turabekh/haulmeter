from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "longhaul-api"
    environment: str = Field(default="dev")
    # extra browser origins allowed to call this API, comma-separated. Empty in the
    # same-origin deployment, where the proxy makes CORS irrelevant.
    cors_origins: str = Field(default="")

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
    minio_bucket: str = Field(default="longhaul")

    # AI-CONTEXT: the same public pk.* token the map already uses. F2 geocodes a
    # parsed receiver address with it; empty means "we cannot place addresses", which
    # the import screen states plainly rather than guessing a coordinate.
    mapbox_token: str = Field(default="")

    # AI-CONTEXT: where a COUNTERPARTY reaches this platform from their inbox. A
    # broker opening a detention notice is outside every session and every origin we
    # control, so a relative link is useless to them — M5's share endpoint returns
    # "/pack/s/<token>" and the client makes it absolute, which an email cannot do.
    # Empty means "we cannot address ourselves", and the notice then says the evidence
    # is available on request rather than printing a link that goes nowhere.
    public_base_url: str = Field(default="")

    smtp_host: str = Field(default="mailpit")
    smtp_port: int = Field(default=1038)

    # F9 AI gateway — real Claude provider activates when a key is present; empty
    # -> the deterministic FakeModelProvider (canned output). Key lives in .env only.
    anthropic_api_key: str = Field(default="")
    # AI-CONTEXT: the id carries NO date suffix — `claude-opus-5` is the complete
    # string, and the dated form this used to hold (`claude-haiku-4-5-20251001`) is the
    # shape that silently 404s when a snapshot is retired.
    #
    # Opus 5 because F9's parses are load-bearing on money: a rate con sets the
    # detention terms a claim is argued from, and a settlement parse is what the
    # auditor compares against. Cost is tuned by EFFORT rather than by model tier —
    # structured parses run at `low`, which is where extraction belongs.
    f9_model: str = Field(default="claude-opus-5")

    # F1 authority verification — real FMCSA QCMobile lookup activates when a webKey
    # is present; empty -> the deterministic FakeAuthorityVerifier. Key in .env only.
    fmcsa_webkey: str = Field(default="")

    # F9 embeddings — Voyage AI (Anthropic's recommended embeddings partner; Anthropic
    # has no embeddings API). Real vectors activate when a key is present; empty -> the
    # deterministic FakeModelProvider embedding. Key in .env only. Model dim = EMBED_DIM.
    voyage_api_key: str = Field(default="")
    embed_model: str = Field(default="voyage-3.5")

    # AI-CONTEXT: Web Push / VAPID (§13.1). Same shape as every provider above — a key
    # present activates real delivery, absent falls back to the recording gateway, so a
    # laptop with no keypair still exercises every tiering decision F8 makes. The pair
    # is SELF-generated (`make vapid-keys`), not issued by anyone, which is the whole
    # reason push is not blocked on a vendor account. Private key in .env only (rule 9).
    vapid_public_key: str = Field(default="")
    vapid_private_key: str = Field(default="")
    # RFC 8292 requires a contact the push service can reach about a misbehaving sender.
    vapid_contact: str = Field(default="mailto:ops@haulmeter.online")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

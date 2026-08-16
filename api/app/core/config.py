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

    # AI-CONTEXT: the ceiling every upload path in this product was missing. F6 has
    # recorded `byte_size` since it was written and nothing ever compared it to anything,
    # so the limit on a document was whatever the machine could decode into memory — from
    # six separate hand-rolled `b64decode` calls, none of which checked.
    #
    # 25 MB is chosen against what the CLIENT now sends rather than against what a phone
    # can produce: captures are downscaled to 2048 px / q0.85 before they leave, which put
    # a 12 MP frame at ~730 KB when it was measured. The headroom is for the paths that do
    # NOT go through that pipeline — a PDF rate con, a portal upload from a desktop
    # scanner — so this rejects the absurd without ever refusing a real document.
    max_upload_mb: int = Field(default=25)

    # AI-CONTEXT: the ceiling on a PDF riding along with a counterparty email. The link is
    # in the body either way, so exceeding this costs a broker one click and never a
    # delivery — while a bounced notice costs the driver the notice. 10 MB sits under the
    # limit most corporate filters enforce; Gmail's own is 25. Measured on real packs:
    # 96 KB median, 196 KB max today, and 2.2 MB for a pack carrying four real photographs.
    max_email_attachment_mb: int = Field(default=10)

    # AI-CONTEXT: signs the short-lived image URLs an `<img src>` can load without a
    # header (api/media.py). Unset is supported and safe — a per-process key is generated
    # and the URLs simply stop working across a restart, which for a one-hour image
    # capability means the next render re-mints them. Set it to keep them stable.
    media_signing_secret: str = Field(default="")
    # one hour: long enough that scrolling a contact sheet never re-mints, short enough
    # that a URL copied out of a browser history is not a lasting grant.
    media_url_ttl_seconds: int = Field(default=3600)

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

    # AI-CONTEXT: the counterparty email transport. These two existed from session 0 and
    # were READ BY NOTHING until 2026-08-02 — there was no SMTP gateway in the codebase at
    # all, so no Stop Packet, detention notice, on-time proof or invoice has ever left the
    # box. Mailpit sat in compose the entire time and received zero messages.
    #
    # The dev defaults ARE the compose service: Mailpit binds MAILPIT_SMTP_PORT (1038)
    # inside the network as well as on the host, so `mailpit:1038` resolves as written.
    smtp_host: str = Field(default="mailpit")
    smtp_port: int = Field(default=1038)
    # who a broker sees the paperwork came from. §12.3: counterparty-facing text is always
    # English, and this is the first thing they read.
    #
    # AI-CONTEXT: this ALSO sets the Message-ID domain (`gateway.py` builds it with
    # `make_msgid(domain=smtp_from.split("@")[-1])`), so it is half of DMARC alignment
    # rather than cosmetic. The default tracks the real sending mailbox — owner cutover
    # 2026-08-16 moved it to the Workspace account on haulmeter.online — because a
    # default naming an address the authenticated account cannot send as would be
    # REWRITTEN by Google rather than refused, shipping a From line nobody chose while
    # F8 records a success.
    smtp_from: str = Field(default="claims@haulmeter.online")
    # a provider that needs credentials gets them here; Mailpit needs none, which is why
    # `configured` turns on HOST rather than on a key (unlike VAPID or the AI gateway).
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")
    # STARTTLS. Off for Mailpit, on for every real provider.
    smtp_starttls: bool = Field(default=False)

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

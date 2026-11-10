"""Runtime configuration, read once from the environment."""

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="OPENLARDER_", extra="ignore")

    database_url: str = "postgresql+psycopg://openlarder:openlarder@localhost:54320/openlarder"
    database_echo: bool = False
    environment: str = "development"

    # Sign-in through the identity broker (Authgear). All three or none:
    # with none, the site runs without sign-in and /api/auth/login says so.
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    # Signs the cookie that carries state and nonce from the redirect to the
    # callback. Required with sign-in, and the same on every instance, or a
    # sign-in that starts on one container and returns to another fails.
    session_secret: str | None = None
    # Where the site is reached, e.g. https://openlarder.com. Required behind
    # a proxy: the callback URL is built from it, and the broker matches that
    # URL exactly. Unset, it is taken from the request, which is right for
    # localhost and wrong behind Coolify's proxy, where the app sees http.
    public_url: str | None = None
    # An archive.org account's API keys, for saving web recipes' pages to the
    # Internet Archive (archive.py). Optional: without them it asks as an
    # anonymous visitor, with lower limits.
    archive_access_key: str | None = None
    archive_secret_key: str | None = None
    # Off for checks that add web recipes but shouldn't ask the real Internet
    # Archive for anything (the accessibility job in CI, a local run of it).
    archive_web_pages: bool = True
    # Bookshop.org's affiliate ID (buying.py). Buy links show only once it's
    # set: a link that earns nothing isn't shown. *Ray, 2026-11-09.*
    bookshop_affiliate_id: str | None = None

    @field_validator("database_url")
    @classmethod
    def _with_driver(cls, url: str) -> str:
        # Platforms hand out postgres:// URLs; SQLAlchemy would read that as
        # psycopg2, which is not installed.
        for scheme in ("postgres://", "postgresql://"):
            if url.startswith(scheme):
                return "postgresql+psycopg://" + url[len(scheme) :]
        return url

    @field_validator("bookshop_affiliate_id")
    @classmethod
    def _affiliate_digits(cls, value: str | None) -> str | None:
        value = (value or "").strip() or None
        if value is not None and not value.isdigit():
            raise ValueError("OPENLARDER_BOOKSHOP_AFFILIATE_ID is a number, like 12345.")
        return value

    @field_validator("public_url")
    @classmethod
    def _no_trailing_slash(cls, url: str | None) -> str | None:
        return url.rstrip("/") if url else url

    @model_validator(mode="after")
    def _sign_in_complete(self) -> "Settings":
        oidc = {
            "OPENLARDER_OIDC_ISSUER": self.oidc_issuer,
            "OPENLARDER_OIDC_CLIENT_ID": self.oidc_client_id,
            "OPENLARDER_OIDC_CLIENT_SECRET": self.oidc_client_secret,
        }
        if any(oidc.values()):
            missing = [name for name, value in oidc.items() if not value]
            if not self.session_secret:
                missing.append("OPENLARDER_SESSION_SECRET")
            if missing:
                # Refuse to start rather than serve a sign-in button that fails.
                raise ValueError("sign-in is half configured; missing " + ", ".join(missing))
        return self

    @property
    def sign_in_configured(self) -> bool:
        return bool(self.oidc_issuer)

    @property
    def archive_keys(self) -> tuple[str, str] | None:
        if self.archive_access_key and self.archive_secret_key:
            return self.archive_access_key, self.archive_secret_key
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()

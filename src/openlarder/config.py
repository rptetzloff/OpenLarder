"""Runtime configuration, read once from the environment."""

import re
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="OPENLARDER_", extra="ignore")

    database_url: str = "postgresql+psycopg://openlarder:openlarder@localhost:54320/openlarder"
    database_echo: bool = False
    # "production", or anything else ("development", "staging"): anything
    # else shows a band on every page saying so (routers/site.py).
    environment: str = "development"
    # A line for the band on every page, in any environment, in place of
    # the environment's own ("Down for maintenance at 9pm"). Plain text.
    notice: str | None = None
    # <meta> tags for every page's head, by name: site verification for
    # affiliate programmes and search engines, as JSON, e.g.
    # {"impact-site-verification": "56d1..."}. Their values are public.
    meta_tags: dict[str, str] = {}

    @field_validator("meta_tags")
    @classmethod
    def _meta_tags_plain(cls, tags: dict[str, str]) -> dict[str, str]:
        for name, value in tags.items():
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,63}", name):
                raise ValueError(f"OPENLARDER_META_TAGS: {name!r} isn't a tag name")
            if not value or len(value) > 500 or not value.isprintable():
                raise ValueError(f"OPENLARDER_META_TAGS: {name}'s value is empty or too long")
        return tags

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
    # Buy links (buying.py), each shown only once its setting is here: a link
    # that earns nothing isn't shown. *Ray, 2026-11-09.* Bookshop.org's
    # affiliate ID, and Amazon's Associates tag ("openlarder-20").
    bookshop_affiliate_id: str | None = None
    amazon_tag: str | None = None
    # The others come through affiliate networks: each is the network's
    # deep-link template, https, with {url} where the shop's address goes.
    barnes_noble_link: str | None = None
    thriftbooks_link: str | None = None
    bookoutlet_link: str | None = None
    kobo_link: str | None = None
    # Limits on /api from outside the site (ratelimit.py): without a key,
    # per address; with one, per key, about ten times as much. Plain reads
    # and searches a minute, and all requests a day (UTC). *Ray, 2026-11-09:
    # start low, loosen once there's real traffic.*
    api_reads_per_minute: int = 60
    api_searches_per_minute: int = 10
    api_requests_per_day: int = 1000
    api_key_reads_per_minute: int = 600
    api_key_searches_per_minute: int = 100
    api_key_requests_per_day: int = 10000

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

    @field_validator("amazon_tag")
    @classmethod
    def _tag_shape(cls, value: str | None) -> str | None:
        value = (value or "").strip() or None
        if value is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,63}", value):
            raise ValueError("OPENLARDER_AMAZON_TAG is an Associates tag, like openlarder-20.")
        return value

    @field_validator("barnes_noble_link", "thriftbooks_link", "bookoutlet_link", "kobo_link")
    @classmethod
    def _deep_link(cls, value: str | None, info) -> str | None:
        value = (value or "").strip() or None
        if value is not None and not (value.startswith("https://") and "{url}" in value):
            name = f"OPENLARDER_{info.field_name.upper()}"
            raise ValueError(
                f"{name} is the affiliate network's deep link, starting https:// and with"
                " {url} where the shop's address goes."
            )
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

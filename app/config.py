"""Runtime configuration. Secrets arrive from the environment, never the repo."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Keys that callers of this API present in X-API-Key, comma separated.
    api_keys: str = ""

    # The opaque handle callers reference. Bound to the API keys below, so a
    # caller cannot use a handle that is not theirs -- see app/credentials.py.
    auth_id: str = "b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512"

    # The backend LinkedIn session. See .env.example for where to find these.
    linkedin_li_at: str = ""
    linkedin_jsessionid: str = ""

    cache_ttl_seconds: int = 21600  # 6h — profiles change rarely; fetchedAt discloses age
    rate_limit_per_minute: int = 30

    @property
    def accepted_api_keys(self) -> frozenset[str]:
        return frozenset(k.strip() for k in self.api_keys.split(",") if k.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()

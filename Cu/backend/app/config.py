from functools import lru_cache
from pathlib import Path
from typing import List
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def _normalize_db_url(url: str) -> str:
    """Accept the URI copied from the Supabase dashboard."""
    import re
    from urllib.parse import quote_plus

    url = (url or "").strip().strip('"').strip("'")
    if not url:
        return url
    # Dashboard copies postgresql://postgres:[YOUR-PASSWORD]@host... — brackets must not stay in the URI.
    bracket = re.match(
        r"^(postgres(?:ql)?://)([^:/]+):\[([^\]]+)\]@(.+)$",
        url,
        re.IGNORECASE,
    )
    if bracket:
        scheme, user, password, rest = bracket.groups()
        url = f"{scheme}{user}:{quote_plus(password)}@{rest}"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+psycopg" not in url.split("://", 1)[0]:
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    host = (parsed.hostname or "").lower()
    if "supabase.co" in host or "supabase.com" in host:
        if "sslmode" not in query:
            query["sslmode"] = ["require"]
        url = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(BACKEND_DIR / ".env"), str(PROJECT_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = ""
    supabase_db_url: str = ""
    supabase_db_password: str = ""
    supabase_project_ref: str = ""
    supabase_db_host: str = ""
    supabase_pooler_host: str = ""
    supabase_region: str = "ap-south-1"

    secret_key: str = "change-this-to-a-long-random-string"
    access_token_expire_minutes: int = 60 * 24 * 7
    algorithm: str = "HS256"

    data_gov_in_api_base: str = "https://api.data.gov.in/resource"
    data_gov_in_api_key: str = ""
    data_gov_in_resource_id: str = "9ef84268-d588-465a-a308-a864a43d0070"
    data_gov_in_fallback_resource_id: str = "35985678-0d79-46b4-9ed6-6f13308a1d24"

    mandi_sync_max_records: int = 2000
    mandi_sync_states: str = "Maharashtra,Karnataka,Madhya Pradesh,Gujarat,Rajasthan"

    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_geocode_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    openweather_api_key: str = ""
    openweather_base_url: str = "https://api.openweathermap.org/data/2.5"

    osrm_base_url: str = "https://router.project-osrm.org"

    sync_interval_minutes: int = 180
    weather_sync_interval_minutes: int = 60

    admin_email: str = "admin@farmdss.local"
    admin_password: str = "ChangeMeAdmin1!"
    demo_farmer_email: str = "farmer@farmdss.local"
    demo_farmer_password: str = "ChangeMeFarmer1!"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def mandi_states(self) -> List[str]:
        return [s.strip() for s in self.mandi_sync_states.split(",") if s.strip()]

    def resolved_database_url(self) -> str:
        if self.supabase_db_url:
            return _normalize_db_url(self.supabase_db_url)
        if self.database_url:
            return _normalize_db_url(self.database_url)
        if self.supabase_db_password and (self.supabase_db_host or self.supabase_project_ref):
            from urllib.parse import quote_plus

            password = quote_plus(self.supabase_db_password.strip().strip('"').strip("'"))
            if self.supabase_pooler_host:
                host = self.supabase_pooler_host
                user = f"postgres.{self.supabase_project_ref}" if self.supabase_project_ref else "postgres"
                return f"postgresql+psycopg://{user}:{password}@{host}/postgres?sslmode=require"
            host = self.supabase_db_host or f"db.{self.supabase_project_ref}.supabase.co"
            user = "postgres"
            return f"postgresql+psycopg://{user}:{password}@{host}:5432/postgres?sslmode=require"
        return "sqlite:///./farmdss.db"

    @property
    def is_sqlite(self) -> bool:
        return self.resolved_database_url().startswith("sqlite")

    @property
    def is_supabase(self) -> bool:
        url = self.resolved_database_url().lower()
        return "supabase.co" in url or "supabase.com" in url


@lru_cache
def get_settings() -> Settings:
    return Settings()

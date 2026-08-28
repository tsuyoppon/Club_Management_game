from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = Field("club-management-api", description="Application name")
    database_url: str = Field(
        "postgresql+psycopg2://postgres:postgres@db:5432/club_game",
        description="Database connection string",
        env="DATABASE_URL",
    )
    api_prefix: str = Field("/api", env="API_PREFIX")
    web_session_cookie: str = Field("club_game_session", env="WEB_SESSION_COOKIE")
    web_session_ttl_days: int = Field(14, env="WEB_SESSION_TTL_DAYS")
    web_cookie_secure: bool = Field(False, env="WEB_COOKIE_SECURE")
    game_backup_root: str = Field("/backups", env="GAME_BACKUP_ROOT")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    return Settings()

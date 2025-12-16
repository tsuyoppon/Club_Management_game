from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    app_name: str = Field("club-management-api", description="Application name")
    database_url: str = Field(
        "postgresql+psycopg2://postgres:postgres@db:5432/club_game",
        description="Database connection string",
        env="DATABASE_URL",
    )
    api_prefix: str = "/api"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    return Settings()

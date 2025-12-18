from fastapi import FastAPI

from .config import get_settings
from .routers import finance, games, health, seasons, turns

settings = get_settings()

app = FastAPI(title=settings.app_name)
app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(games.router, prefix=settings.api_prefix)
app.include_router(seasons.router, prefix=settings.api_prefix)
app.include_router(turns.router, prefix=settings.api_prefix)
app.include_router(finance.router, prefix=settings.api_prefix)


@app.get("/")
def read_root():
    return {"message": "Welcome to the club management training API"}

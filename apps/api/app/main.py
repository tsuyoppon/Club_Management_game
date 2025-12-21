from fastapi import FastAPI

from .config import get_settings
from .routers import finance, games, health, seasons, turns, finance_structural, management, fanbase, sponsors, bankruptcy, disclosures

settings = get_settings()

app = FastAPI(title=settings.app_name)
app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(games.router, prefix=settings.api_prefix)
app.include_router(seasons.router, prefix=settings.api_prefix)
app.include_router(turns.router, prefix=settings.api_prefix)
app.include_router(finance.router, prefix=settings.api_prefix)
app.include_router(finance_structural.router, prefix=settings.api_prefix)
app.include_router(management.router, prefix=settings.api_prefix)
app.include_router(fanbase.router, prefix=settings.api_prefix)
app.include_router(sponsors.router, prefix=settings.api_prefix)
app.include_router(bankruptcy.router)  # PR8: 債務超過関連API
app.include_router(disclosures.router, prefix=settings.api_prefix)  # PR9: 情報公開イベントAPI


@app.get("/")
def read_root():
    return {"message": "Welcome to the club management training API"}

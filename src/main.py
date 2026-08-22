# src/main.py
from fastapi import FastAPI

# Side-effect imports for tool registration
import src.tools  # noqa: F401

from src.routes.webhook import router as webhook_router
from src.routes.telegram import router as telegram_router
from src.tools.mpesa import mpesa_router
from src.uptime import lifespan

app = FastAPI(
    title="Realtors Round Tables API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(webhook_router)
app.include_router(telegram_router)
app.include_router(mpesa_router)


@app.get("/uptime")
async def get_uptime():
    return {"uptime": "Simon (Realtors Round Tables) is up and running!"}
# src/main.py
from fastapi import FastAPI

# Side-effect imports for tool registration
import src.tools  # noqa: F401

from src.routes.webhook import router as webhook_router
from src.tools.mpesa import mpesa_router

app = FastAPI(
    title="Samantha API",
    version="1.0.0",
)

app.include_router(webhook_router)
app.include_router(mpesa_router)
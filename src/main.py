# src/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

# Side-effect imports for tool registration
import src.tools  # noqa: F401

from src.routes.webhook import router as webhook_router
from src.routes.telegram import router as telegram_router
from src.routes.properties import router as properties_router
from src.routes.chat import router as chat_router
from src.tools.mpesa import mpesa_router
from src.uptime import lifespan

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(
    title="Realtors Round Tables API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: allow the external website to call the API from a different domain.
# Configure via CORS_ALLOWED_ORIGINS env var (comma-separated list),
# or leave unset to allow all origins (development convenience).
_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(telegram_router)
app.include_router(properties_router)
app.include_router(chat_router)
app.include_router(mpesa_router)

# Serve the embeddable Samantha chat widget as a static asset so an external
# website owner can drop a single <script> tag onto their page.
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/uptime")
async def get_uptime():
    return {"uptime": "Simon (Realtors Round Tables) is up and running!"}
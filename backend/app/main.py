# app/main.py — Application entry point.
#
# This file creates the FastAPI app, configures it, and registers all routers.
# When you run `uvicorn app.main:app`, uvicorn imports this file and starts
# serving the `app` object defined below.

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, recommend

# ── Load environment variables ─────────────────────────────────────────────────
# Reads key=value pairs from the .env file into os.environ.
# Must happen before any code that reads environment variables.
load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
# basicConfig sets the format for all log messages across the app.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── App instance ──────────────────────────────────────────────────────────────
# FastAPI() creates the application. The metadata here powers the auto-generated
# docs page at http://localhost:8000/docs
app = FastAPI(
    title="AI Fishing Copilot API",
    description=(
        "Backend for the AI Fishing Copilot. "
        "Accepts a postcode and returns a fishing recommendation "
        "powered by Vertex AI and a FAISS knowledge base."
    ),
    version="0.1.0",
)

# ── CORS middleware ────────────────────────────────────────────────────────────
# CORS (Cross-Origin Resource Sharing) controls which domains can call this API.
# Without this, the browser blocks requests from the frontend (different port).
# In production, replace "*" with your actual frontend URL.
allowed_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
allowed_origins = [origin.strip() for origin in allowed_origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # e.g. ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],   # allow GET, POST, OPTIONS, etc.
    allow_headers=["*"],   # allow any request headers
)

# ── Register routers ──────────────────────────────────────────────────────────
# Each router is defined in its own file under app/routers/.
# `include_router` mounts all of its endpoints onto the main app.
app.include_router(health.router)
app.include_router(recommend.router)

logger.info("AI Fishing Copilot API started — docs at http://localhost:8000/docs")

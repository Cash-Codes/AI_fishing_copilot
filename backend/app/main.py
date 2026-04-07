# app/main.py — Application entry point.
#
# This file creates the FastAPI app, configures it, and registers all routers.
# When you run `uvicorn app.main:app`, uvicorn imports this file and starts
# serving the `app` object defined below.

import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, recommend
from app.settings import get_settings

# ── Load environment variables ─────────────────────────────────────────────────
# Reads key=value pairs from the .env file into os.environ.
# Must happen before Settings() is constructed so all env vars are visible.
load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── App instance ──────────────────────────────────────────────────────────────
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
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ──────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(recommend.router)

# ── Startup log ───────────────────────────────────────────────────────────────
# Print a clear summary of the active configuration so operators can confirm
# the app started with the right settings without reading every env var.

def _vertex_status(s) -> str:
    if not s.enable_vertex_ai:
        return "disabled  (ENABLE_VERTEX_AI=false)"
    if not s.google_cloud_project:
        return (
            "disabled  (ENABLE_VERTEX_AI=true but GOOGLE_CLOUD_PROJECT is not set "
            "— set it to enable AI explanations)"
        )
    return (
        f"enabled   (project={s.google_cloud_project}, "
        f"model={s.vertex_ai_model}, "
        f"region={s.google_cloud_region})"
    )


def _mock_status(s) -> str:
    if s.enable_mock_fallback:
        return "enabled   (weather falls back to deterministic mock on API failure)"
    return "disabled  (real weather API required — errors will surface if unreachable)"


logger.info("AI Fishing Copilot API ready")
logger.info("  vertex_ai     : %s", _vertex_status(settings))
logger.info("  mock_fallback : %s", _mock_status(settings))
logger.info("  cors          : %s", settings.cors_allowed_origins)
logger.info("  docs          : http://%s:%d/docs", settings.backend_host, settings.backend_port)

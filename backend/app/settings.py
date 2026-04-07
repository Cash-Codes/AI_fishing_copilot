# app/settings.py — Centralised application configuration.
#
# All configuration is read from environment variables (with sensible defaults
# for local development).  Variables can be set in a .env file — copy
# .env.example and fill in the values you need.
#
# Usage anywhere in the app:
#   from app.settings import get_settings
#   settings = get_settings()
#
# get_settings() creates a fresh Settings object on every call so that
# os.environ patches in tests are always reflected.

from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Pydantic-settings maps each field to an uppercase env var of the same name,
    so `google_cloud_project` reads from GOOGLE_CLOUD_PROJECT, etc.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",        # silently ignore unknown env vars
    )

    # ── Server ────────────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_allowed_origins: str = "http://localhost:3000"

    # ── Feature flags ─────────────────────────────────────────────────────────
    # ENABLE_VERTEX_AI   — set to false to force template explanations even when
    #                      GOOGLE_CLOUD_PROJECT is configured (e.g. cost control,
    #                      offline demo, or canary testing the template).
    #                      Defaults to true so existing deployments are unaffected.
    enable_vertex_ai: bool = True

    # ENABLE_MOCK_FALLBACK — when true (default), weather data falls back to a
    #                        deterministic mock if the Open-Meteo API is unreachable.
    #                        Set to false in production if you require real data
    #                        and want a visible error instead of silently serving
    #                        mock conditions.
    enable_mock_fallback: bool = True

    # ── Vertex AI / GCP ───────────────────────────────────────────────────────
    google_cloud_project: str = ""
    google_cloud_region: str = "us-central1"
    vertex_ai_model: str = "gemini-2.5-flash"

    # ── Derived helpers ───────────────────────────────────────────────────────

    @property
    def cors_origins_list(self) -> List[str]:
        """Split CORS_ALLOWED_ORIGINS on commas and strip whitespace."""
        return [o.strip() for o in self.cors_allowed_origins.split(",")]

    @property
    def vertex_ai_ready(self) -> bool:
        """True only when both the feature flag and a GCP project are configured."""
        return self.enable_vertex_ai and bool(self.google_cloud_project)


def get_settings() -> Settings:
    """Return application settings, freshly read from the environment.

    Not cached so that os.environ patches in tests take effect immediately.
    Creating a Settings object is cheap (a few env-var reads), so this is
    fine to call at request time.
    """
    return Settings()

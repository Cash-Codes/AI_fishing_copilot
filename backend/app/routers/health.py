# routers/health.py — A simple liveness check endpoint.
#
# GET /health is a standard pattern in web services.
# Load balancers and monitoring tools hit this URL to confirm the app is alive.
# It should always return quickly and never depend on external services.

from fastapi import APIRouter

from app.models.response import HealthResponse

# APIRouter groups related endpoints together.
# We include this router in main.py — this keeps each file focused.
router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns `ok` if the service is running.",
)
def health_check() -> HealthResponse:
    """
    Liveness probe — used by monitoring tools and load balancers.
    Always returns HTTP 200 with status 'ok' if the service is up.
    """
    return HealthResponse(status="ok", version="0.1.0")

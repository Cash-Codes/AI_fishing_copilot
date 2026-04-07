"""
conftest.py — Shared pytest fixtures.

pytest automatically loads this file before any test module.
Fixtures defined here are available to every test without needing an import.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    """
    FastAPI TestClient — calls the app directly in-process, no real server.

    TestClient is a thin wrapper around httpx that uses Starlette's ASGI
    transport under the hood. It lets us write plain synchronous tests
    (no async/await needed) while still exercising the full request/response
    cycle including middleware and Pydantic validation.

    Usage in a test:
        def test_something(client):
            response = client.get("/health")
            assert response.status_code == 200
    """
    with TestClient(app) as c:
        yield c

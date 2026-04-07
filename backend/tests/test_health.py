"""
test_health.py — Tests for GET /health.

Small, but valuable: if this endpoint breaks something is wrong with the
app factory (main.py) itself, not just a specific feature.
"""


def test_health_returns_200(client):
    """The endpoint must always be reachable."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_body(client):
    """Status must be 'ok' — monitoring tools string-match this field."""
    body = client.get("/health").json()
    assert body["status"] == "ok"


def test_health_includes_version(client):
    """Version field helps operators confirm which build is running."""
    body = client.get("/health").json()
    assert "version" in body
    assert body["version"] is not None

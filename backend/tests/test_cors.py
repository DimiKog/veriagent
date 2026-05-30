import pytest
from fastapi.testclient import TestClient

from app.main import CORS_ALLOWED_ORIGINS, app

client = TestClient(app)


@pytest.mark.parametrize("origin", CORS_ALLOWED_ORIGINS)
def test_cors_preflight_allows_configured_origins(origin: str):
    response = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "GET" in response.headers["access-control-allow-methods"]
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "OPTIONS" in response.headers["access-control-allow-methods"]


@pytest.mark.parametrize("origin", CORS_ALLOWED_ORIGINS)
def test_cors_get_includes_allow_origin_for_configured_origins(origin: str):
    response = client.get("/health", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_unlisted_origin():
    response = client.get(
        "/health",
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_post_allows_github_pages_origin():
    response = client.post(
        "/audit/batches",
        headers={"Origin": "https://dimikog.github.io"},
    )

    assert response.status_code == 400
    assert response.headers["access-control-allow-origin"] == "https://dimikog.github.io"

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["STORAGE_PATH"] = "./storage/test"
os.environ["AUTO_CREATE_TABLES"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


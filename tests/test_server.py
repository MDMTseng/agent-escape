"""Tests for the server module — verifies app creation and endpoints."""

import pytest
from fastapi.testclient import TestClient

from agenttown.server import app


@pytest.fixture
def client():
    # Use TestClient without lifespan to avoid running the simulation
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_index_returns_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "AgentTown" in response.text
    assert "text/html" in response.headers["content-type"]


def test_api_state_without_simulation(client):
    response = client.get("/api/state")
    # Without lifespan, sim_world is None
    assert response.status_code == 200

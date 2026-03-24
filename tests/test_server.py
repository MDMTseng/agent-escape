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


def test_api_themes_returns_all_themes(client):
    response = client.get("/api/themes")
    assert response.status_code == 200
    data = response.json()
    assert "themes" in data
    assert "gothic_manor" in data["themes"]
    assert "sci_fi_lab" in data["themes"]
    assert "ancient_tomb" in data["themes"]
    # Each theme has rooms and characters
    for key, theme in data["themes"].items():
        assert "rooms" in theme
        assert "characters" in theme
        assert len(theme["rooms"]) > 0
        assert len(theme["characters"]) > 0


def test_api_generate_story_missing_body(client):
    response = client.post("/api/generate-story")
    assert response.status_code == 200
    data = response.json()
    assert "error" in data


def test_api_generate_story_missing_premise(client):
    response = client.post("/api/generate-story", json={"theme": "gothic_manor"})
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    assert "Premise" in data["error"]


def test_api_generate_story_invalid_theme(client):
    response = client.post("/api/generate-story", json={
        "theme": "nonexistent_theme",
        "premise": "A test story",
    })
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    assert "Invalid theme" in data["error"]


def test_api_generate_story_invalid_difficulty(client):
    response = client.post("/api/generate-story", json={
        "theme": "gothic_manor",
        "premise": "A test story",
        "difficulty": 10,
    })
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    assert "Difficulty" in data["error"]


def test_api_generate_story_invalid_num_characters(client):
    response = client.post("/api/generate-story", json={
        "theme": "gothic_manor",
        "premise": "A test story",
        "num_characters": 1,
    })
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    assert "num_characters" in data["error"]


def test_api_generate_story_success(client):
    response = client.post("/api/generate-story", json={
        "theme": "gothic_manor",
        "premise": "A paranoid alchemist hid his formula in a trapped laboratory",
        "difficulty": 3,
        "num_characters": 3,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert data["rooms"] >= 4
    assert data["agents"] == 2
    assert data["chain_steps"] >= 1
    assert "world_bible" in data
    assert data["world_bible"]["theme"] == "gothic_manor"
    assert len(data["world_bible"]["characters"]) == 3

"""Tests for FastAPI REST API."""
import pytest

from btcu_harness.api import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthAndRoot:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert data["space_size"] == 19683

    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert "BTCU" in data["name"]
        assert "/api/init" in data["endpoints"]


class TestInit:
    def test_init_agent(self, client):
        r = client.post("/api/init", json={"domain": "agent"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "initialized"
        assert len(data["dimensions"]) == 9

    def test_init_decision(self, client):
        r = client.post("/api/init", json={"domain": "decision"})
        assert r.status_code == 200

    def test_init_custom_with_dims(self, client):
        r = client.post("/api/init", json={
            "domain": "custom",
            "dims": "a,b,c,d,e,f,g,h,i",
        })
        assert r.status_code == 200

    def test_init_custom_without_dims_fails(self, client):
        r = client.post("/api/init", json={"domain": "custom"})
        assert r.status_code == 400

    def test_init_with_mission(self, client):
        r = client.post("/api/init", json={
            "domain": "agent",
            "mission": "save the world",
        })
        assert r.status_code == 200


class TestExplore:
    def test_explore_by_index(self, client):
        r = client.get("/api/explore", params={"index": 100})
        assert r.status_code == 200
        data = r.json()
        assert data["index"] == 100
        assert len(data["values"]) == 9
        assert "neighbors" in data

    def test_explore_all_void(self, client):
        r = client.get("/api/explore", params={"index": 9841})
        assert r.status_code == 200
        data = r.json()
        assert data["void_count"] == 9

    def test_explore_by_values(self, client):
        r = client.get("/api/explore", params={"values": "1,0,-1,1,0,-1,1,0,-1"})
        assert r.status_code == 200
        data = r.json()
        assert data["values"] == [1, 0, -1, 1, 0, -1, 1, 0, -1]

    def test_explore_no_params_fails(self, client):
        r = client.get("/api/explore")
        assert r.status_code == 400

    def test_explore_invalid_index(self, client):
        r = client.get("/api/explore", params={"index": 99999})
        assert r.status_code == 400  # Out of range


class TestStatusAndSave:
    def test_status_without_init(self, client):
        # Need to reset global state first
        import btcu_harness.api as api_module
        api_module._agent = None
        r = client.get("/api/status")
        assert r.status_code == 400

    def test_full_pipeline(self, client):
        # Init
        r = client.post("/api/init", json={"domain": "agent"})
        assert r.status_code == 200

        # Status
        r = client.get("/api/status")
        assert r.status_code == 200
        # status() returns a string
        body = r.json()
        assert isinstance(body, str) and "BTCU" in body or "BTCU" in str(body)

        # Save
        r = client.post("/api/save")
        assert r.status_code == 200
        assert r.json()["status"] == "saved"

        # Seasons
        r = client.get("/api/seasons")
        assert r.status_code == 200

        # Climate
        r = client.get("/api/climate")
        assert r.status_code == 200

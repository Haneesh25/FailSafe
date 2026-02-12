"""Tests for dashboard server and WebSocket."""

import pytest
from starlette.testclient import TestClient

from failsafe.core.engine import FailSafe
from failsafe.dashboard.server import create_app


@pytest.fixture
def fs():
    fs = FailSafe(mode="warn", audit_db=":memory:")
    fs.register_agent("kyc_agent", description="KYC verification")
    fs.register_agent("onboarding_agent", description="Onboarding flow")
    fs.contract(
        name="kyc-to-onboarding",
        source="kyc_agent",
        target="onboarding_agent",
        allow=["name", "status"],
        deny=["ssn"],
    )
    return fs


@pytest.fixture
def client(fs):
    app = create_app(fs)
    with TestClient(app) as c:
        yield c


class TestRESTEndpoints:
    def test_get_agents(self, client):
        response = client.get("/api/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 2
        names = {a["name"] for a in agents}
        assert "kyc_agent" in names
        assert "onboarding_agent" in names

    def test_get_contracts(self, client):
        response = client.get("/api/contracts")
        assert response.status_code == 200
        contracts = response.json()
        assert len(contracts) == 1
        assert contracts[0]["name"] == "kyc-to-onboarding"

    def test_get_coverage(self, client):
        response = client.get("/api/coverage")
        assert response.status_code == 200
        matrix = response.json()
        assert matrix["kyc_agent"]["onboarding_agent"] == "covered"

    def test_get_graph(self, client):
        response = client.get("/api/graph")
        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1

    def test_get_validations_empty(self, client):
        response = client.get("/api/validations")
        assert response.status_code == 200
        assert response.json() == []


class TestWebSocket:
    def test_websocket_connection(self, client):
        with client.websocket_connect("/ws") as ws:
            pass

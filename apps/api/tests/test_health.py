from __future__ import annotations


def test_health_endpoint_reports_database_status(client) -> None:
    # Test both /health and /healthz
    for path in ["/health", "/healthz"]:
        response = client.get(path)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"
        assert data["version"] == "0.1.0"
        assert data["environment"] == "test"


def test_liveness_and_readiness_probes(client) -> None:
    live_resp = client.get("/health/live")
    assert live_resp.status_code == 200
    assert live_resp.json() == {"status": "alive"}

    ready_resp = client.get("/health/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json() == {"status": "ready"}

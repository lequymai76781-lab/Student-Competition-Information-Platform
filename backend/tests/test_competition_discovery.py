from fastapi.testclient import TestClient


def test_get_competition_discovery_985_progress(client: TestClient) -> None:
    response = client.get("/api/v0.6/competitions/discovery/985-progress")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["scanned_985_count"] == 0
    assert body["data"]["progress"] == []


def test_get_v08_competition_discovery_coverage(client: TestClient) -> None:
    response = client.get("/api/v0.8/competitions/discovery/coverage")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["universities_985_total"] == 39
    assert data["universities_211_non_985_total"] == 73
    assert data["progress_985"] == []
    assert data["progress_211_non_985"] == []

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import psycopg2
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


@pytest.fixture
def db_available():
    """Skip DB-backed tests if no database is reachable — lets the suite
    run locally without Postgres, while CI always has a real one via a
    service container."""
    if not os.environ.get("DB_HOST"):
        pytest.skip("DB_HOST not set — no database configured for this run")
    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ.get("DB_NAME", "appdb"),
            user=os.environ.get("DB_USER", "appadmin"),
            password=os.environ.get("DB_PASSWORD", ""),
            connect_timeout=3,
        )
        conn.close()
    except Exception as e:
        pytest.skip(f"database not reachable: {e}")


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_status_returns_expected_fields(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.get_json()
    assert "hostname" in data
    assert "uptime_seconds" in data
    assert "version" in data
    assert "server_time" in data


def test_status_uptime_is_nonnegative(client):
    response = client.get("/api/status")
    assert response.get_json()["uptime_seconds"] >= 0


def test_index_lists_endpoints(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.get_json()
    assert "/health" in data["endpoints"]
    assert "/api/status" in data["endpoints"]
    assert "/api/visits" in data["endpoints"]


def test_unknown_route_returns_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404


def test_visits_without_db_returns_503(client, monkeypatch):
    """When no DB is configured, /api/visits should fail gracefully, not crash."""
    monkeypatch.delenv("DB_HOST", raising=False)
    response = client.get("/api/visits")
    assert response.status_code == 503


def test_visits_increments_with_real_db(client, db_available):
    first = client.get("/api/visits").get_json()["visits"]
    second = client.get("/api/visits").get_json()["visits"]
    assert second == first + 1


def test_visits_summary_without_db_returns_503(client, monkeypatch):
    monkeypatch.delenv("DB_HOST", raising=False)
    response = client.get("/api/visits/summary")
    assert response.status_code == 503


def test_visits_summary_returns_expected_shape(client, db_available):
    # Make sure at least one visit exists to summarize
    client.get("/api/visits")

    response = client.get("/api/visits/summary")
    assert response.status_code == 200
    data = response.get_json()

    assert "total" in data
    assert "last_24h" in data
    assert "hourly" in data
    assert data["total"] >= 1
    assert data["last_24h"] >= 1


def test_visits_summary_hourly_has_24_buckets_in_order(client, db_available):
    response = client.get("/api/visits/summary")
    data = response.get_json()

    hourly = data["hourly"]
    assert len(hourly) == 24
    for bucket in hourly:
        assert "hour" in bucket
        assert "count" in bucket
        assert bucket["count"] >= 0

    # Every hour label should be a valid "HH:00" format
    hours = [int(b["hour"].split(":")[0]) for b in hourly]
    assert all(0 <= h <= 23 for h in hours)
    assert all(b["hour"].endswith(":00") for b in hourly)


def test_visits_summary_last_24h_matches_sum_of_hourly(client, db_available):
    client.get("/api/visits")
    response = client.get("/api/visits/summary")
    data = response.get_json()

    assert data["last_24h"] == sum(b["count"] for b in data["hourly"])

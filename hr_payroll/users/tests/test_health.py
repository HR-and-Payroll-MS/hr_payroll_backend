from http import HTTPStatus
from unittest import mock

import pytest
from django.db import connection as dj_conn


class DummyDbError(Exception):  # TRY002: use a custom exception in tests
    """Synthetic DB error for testing."""


@pytest.mark.django_db
def test_health_ok(client):
    resp = client.get("/health/")
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    assert data["status"] == "ok"
    assert data["components"]["db"]["ok"] is True
    assert "redis" in data["components"]


@pytest.mark.django_db
def test_health_degraded_when_redis_fails(client):
    with mock.patch(
        "config.health.redis.Redis.ping",
        side_effect=TimeoutError("redis timeout"),  # E501: wrapped in parens
    ):
        resp = client.get("/health/")
    assert resp.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    data = resp.json()
    assert data["components"]["redis"]["ok"] is False
    assert data["status"] in {"degraded", "down"}


@pytest.mark.django_db
def test_health_degraded_when_db_fails(client, monkeypatch):
    msg = "db down"  # EM101/TRY003: assign message to a variable

    def raise_cursor():
        raise DummyDbError(msg)

    monkeypatch.setattr(dj_conn, "cursor", raise_cursor, raising=True)
    resp = client.get("/health/")
    assert resp.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    data = resp.json()
    assert data["components"]["db"]["ok"] is False

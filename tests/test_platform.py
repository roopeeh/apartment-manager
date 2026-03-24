import uuid
import pytest
from conftest import API


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def test_platform_stats(client, sa_headers):
    resp = client.get(f"{API}/platform/stats", headers=sa_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total_societies" in data


def test_platform_stats_requires_super_admin(client, admin_headers):
    resp = client.get(f"{API}/platform/stats", headers=admin_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# List societies
# ---------------------------------------------------------------------------

def test_list_societies(client, sa_headers):
    resp = client.get(f"{API}/platform/societies", headers=sa_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert "pagination" in body


def test_list_societies_search(client, sa_headers, test_society):
    name = test_society["society"]["name"]
    resp = client.get(f"{API}/platform/societies", headers=sa_headers, params={"search": name[:10]})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert any(s["id"] == test_society["society_id"] for s in data)


def test_list_societies_pagination(client, sa_headers):
    resp = client.get(f"{API}/platform/societies", headers=sa_headers, params={"page": 1, "limit": 2})
    assert resp.status_code == 200
    assert resp.json()["pagination"]["limit"] == 2


# ---------------------------------------------------------------------------
# Create society
# ---------------------------------------------------------------------------

def test_create_society(client, sa_headers):
    uid = uuid.uuid4().hex[:8]
    resp = client.post(f"{API}/platform/societies", headers=sa_headers, json={
        "name": f"New Society {uid}",
        "address": "456 New Street",
        "city": "New City",
        "total_blocks": 1,
        "blocks": ["C"],
        "floors": [],
        "admin": {
            "name": f"New Admin {uid}",
            "email": f"newadmin_{uid}@test.com",
            "password": "Test@1234",
            "phone": "9333333333",
        },
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["society"]["name"] == f"New Society {uid}"


def test_create_society_requires_super_admin(client, admin_headers):
    uid = uuid.uuid4().hex[:8]
    resp = client.post(f"{API}/platform/societies", headers=admin_headers, json={
        "name": f"Forbidden Society {uid}",
        "address": "x",
        "city": "x",
        "total_blocks": 0,
        "blocks": [],
        "floors": [],
        "admin": {"name": "x", "email": f"x_{uid}@test.com", "password": "Test@1234"},
    })
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Update society
# ---------------------------------------------------------------------------

def test_update_society(client, sa_headers, society_id):
    resp = client.put(f"{API}/platform/societies/{society_id}", headers=sa_headers, json={
        "city": "Updated City",
    })
    assert resp.status_code == 200
    assert resp.json()["data"]["city"] == "Updated City"


# ---------------------------------------------------------------------------
# Suspend society (creates its own society so we don't break other tests)
# ---------------------------------------------------------------------------

def test_suspend_society(client, sa_headers):
    uid = uuid.uuid4().hex[:8]
    create_resp = client.post(f"{API}/platform/societies", headers=sa_headers, json={
        "name": f"ToSuspend {uid}",
        "address": "1 Suspend St",
        "city": "Suspendville",
        "total_blocks": 0,
        "blocks": [],
        "floors": [],
        "admin": {
            "name": f"Admin {uid}",
            "email": f"suspend_admin_{uid}@test.com",
            "password": "Test@1234",
        },
    })
    assert create_resp.status_code == 200
    sid = create_resp.json()["data"]["society"]["id"]

    resp = client.delete(f"{API}/platform/societies/{sid}", headers=sa_headers)
    assert resp.status_code == 200

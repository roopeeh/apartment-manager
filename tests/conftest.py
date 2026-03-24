"""
Integration test fixtures.

Required env vars:
  TEST_BASE_URL              - defaults to http://localhost:8000
  TEST_SUPER_ADMIN_EMAIL     - super_admin account email
  TEST_SUPER_ADMIN_PASSWORD  - super_admin account password
"""
import os
import uuid
import pytest
import httpx

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
API = "/api/v1"
SUPER_ADMIN_EMAIL = os.getenv("TEST_SUPER_ADMIN_EMAIL", "")
SUPER_ADMIN_PASSWORD = os.getenv("TEST_SUPER_ADMIN_PASSWORD", "")


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="session")
def uid():
    """Short unique suffix for test data names to avoid collisions."""
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def super_admin_token(client):
    assert SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD, (
        "Set TEST_SUPER_ADMIN_EMAIL and TEST_SUPER_ADMIN_PASSWORD env vars"
    )
    resp = client.post(f"{API}/auth/login", json={
        "email": SUPER_ADMIN_EMAIL,
        "password": SUPER_ADMIN_PASSWORD,
    })
    assert resp.status_code == 200, f"Super admin login failed: {resp.text}"
    return resp.json()["data"]["access_token"]


@pytest.fixture(scope="session")
def sa_headers(super_admin_token):
    return {"Authorization": f"Bearer {super_admin_token}"}


# ---------------------------------------------------------------------------
# Society + admin fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_society(client, sa_headers, uid):
    resp = client.post(f"{API}/platform/societies", headers=sa_headers, json={
        "name": f"Test Society {uid}",
        "address": "1 Integration Test Lane",
        "city": "Testville",
        "total_blocks": 2,
        "blocks": ["A", "B"],
        "floors": [1, 2, 3],
        "admin": {
            "name": f"Admin {uid}",
            "email": f"admin_{uid}@test.com",
            "password": "Test@1234",
            "phone": "9000000001",
        },
    })
    assert resp.status_code == 200, f"Society creation failed: {resp.text}"
    data = resp.json()["data"]
    return {
        "society": data["society"],
        "society_id": data["society"]["id"],
        "admin_email": f"admin_{uid}@test.com",
        "admin_password": "Test@1234",
    }


@pytest.fixture(scope="session")
def society_id(test_society):
    return test_society["society_id"]


@pytest.fixture(scope="session")
def admin_token(client, test_society):
    resp = client.post(f"{API}/auth/login", json={
        "email": test_society["admin_email"],
        "password": test_society["admin_password"],
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["data"]["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# Shared test data fixtures (session-scoped — do not delete these in tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_flat(client, admin_headers, society_id, uid):
    resp = client.post(f"{API}/societies/{society_id}/flats", headers=admin_headers, json={
        "flat_number": f"A{uid[:4]}",
        "block": "A",
        "floor": 1,
        "area": 1200,
        "owner_name": f"Owner {uid}",
        "phone": "9111111111",
        "email": f"owner_{uid}@test.com",
        "occupancy": "occupied",
        "maintenance_amount": 5000.00,
    })
    assert resp.status_code == 200, f"Flat creation failed: {resp.text}"
    return resp.json()["data"]


@pytest.fixture(scope="session")
def flat_id(test_flat):
    return test_flat["id"]


@pytest.fixture(scope="session")
def test_resident(client, admin_headers, society_id, flat_id, uid):
    resp = client.post(f"{API}/societies/{society_id}/residents", headers=admin_headers, json={
        "flat_id": flat_id,
        "name": f"Resident {uid}",
        "phone": "9222222222",
        "email": f"resident_{uid}@test.com",
        "role": "Owner",
        "move_in_date": "2024-01-01",
    })
    assert resp.status_code == 200, f"Resident creation failed: {resp.text}"
    return resp.json()["data"]


@pytest.fixture(scope="session")
def test_payment(client, admin_headers, society_id, flat_id):
    resp = client.post(f"{API}/societies/{society_id}/payments", headers=admin_headers, json={
        "flat_id": flat_id,
        "month": "Jan",
        "year": 2025,
        "amount_paid": 5000.00,
        "payment_mode": "Cash",
        "payment_date": "2025-01-05",
        "remarks": "Integration test payment",
    })
    assert resp.status_code == 200, f"Payment creation failed: {resp.text}"
    return resp.json()["data"]


@pytest.fixture(scope="session")
def test_expense(client, admin_headers, society_id, uid):
    resp = client.post(
        f"{API}/societies/{society_id}/expenses",
        headers=admin_headers,
        data={
            "date": "2025-01-10",
            "title": f"Test Expense {uid}",
            "category": "Maintenance",
            "vendor": "Test Vendor",
            "amount": "2500.00",
            "notes": "Integration test expense",
        },
    )
    assert resp.status_code == 201, f"Expense creation failed: {resp.text}"
    return resp.json()["data"]


@pytest.fixture(scope="session")
def test_notice(client, admin_headers, society_id, uid):
    resp = client.post(f"{API}/societies/{society_id}/notices", headers=admin_headers, json={
        "title": f"Test Notice {uid}",
        "message": "This is an integration test notice.",
        "priority": "medium",
        "pinned": False,
    })
    assert resp.status_code == 200, f"Notice creation failed: {resp.text}"
    return resp.json()["data"]

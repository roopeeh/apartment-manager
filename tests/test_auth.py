import uuid
import pytest
from conftest import API


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def register_user(client, suffix=None):
    suffix = suffix or uuid.uuid4().hex[:8]
    payload = {
        "name": f"Test User {suffix}",
        "email": f"user_{suffix}@test.com",
        "password": "Test@1234",
        "phone": "9000000000",
    }
    resp = client.post(f"{API}/auth/register", json=payload)
    return resp, payload


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def test_register_success(client):
    resp, payload = register_user(client)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["email"] == payload["email"]


def test_register_duplicate_email(client):
    _, payload = register_user(client)
    resp2 = client.post(f"{API}/auth/register", json=payload)
    assert resp2.status_code == 400


def test_register_invalid_email(client):
    resp = client.post(f"{API}/auth/register", json={
        "name": "Bad User",
        "email": "not-an-email",
        "password": "Test@1234",
    })
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_success(client):
    _, payload = register_user(client)
    resp = client.post(f"{API}/auth/login", json={
        "email": payload["email"],
        "password": payload["password"],
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == payload["email"]


def test_login_wrong_password(client):
    _, payload = register_user(client)
    resp = client.post(f"{API}/auth/login", json={
        "email": payload["email"],
        "password": "WrongPassword!",
    })
    assert resp.status_code == 401


def test_login_unknown_email(client):
    resp = client.post(f"{API}/auth/login", json={
        "email": "nobody@nowhere.com",
        "password": "Test@1234",
    })
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------

def test_refresh_token(client):
    _, payload = register_user(client)
    login = client.post(f"{API}/auth/login", json={
        "email": payload["email"],
        "password": payload["password"],
    }).json()["data"]

    resp = client.post(f"{API}/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert resp.status_code == 200
    new_data = resp.json()["data"]
    assert "access_token" in new_data
    assert new_data["access_token"] != login["access_token"]


def test_refresh_invalid_token(client):
    resp = client.post(f"{API}/auth/refresh", json={"refresh_token": "invalid-token"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

def test_logout(client):
    _, payload = register_user(client)
    login = client.post(f"{API}/auth/login", json={
        "email": payload["email"],
        "password": payload["password"],
    }).json()["data"]

    resp = client.post(f"{API}/auth/logout", json={"refresh_token": login["refresh_token"]})
    assert resp.status_code == 200

    # Token should be revoked — refresh should now fail
    resp2 = client.post(f"{API}/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert resp2.status_code == 401


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

def test_change_password(client):
    _, payload = register_user(client)
    login = client.post(f"{API}/auth/login", json={
        "email": payload["email"],
        "password": payload["password"],
    }).json()["data"]
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    resp = client.post(f"{API}/auth/change-password", headers=headers, json={
        "current_password": payload["password"],
        "new_password": "NewTest@5678",
    })
    assert resp.status_code == 200

    # Old password should no longer work
    resp2 = client.post(f"{API}/auth/login", json={
        "email": payload["email"],
        "password": payload["password"],
    })
    assert resp2.status_code == 401


def test_change_password_wrong_current(client):
    _, payload = register_user(client)
    login = client.post(f"{API}/auth/login", json={
        "email": payload["email"],
        "password": payload["password"],
    }).json()["data"]
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    resp = client.post(f"{API}/auth/change-password", headers=headers, json={
        "current_password": "WrongCurrent!",
        "new_password": "NewTest@5678",
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Forgot / reset password
# ---------------------------------------------------------------------------

def test_forgot_password_always_succeeds(client):
    # Should return 200 even for unknown email (security best practice)
    resp = client.post(f"{API}/auth/forgot-password", json={"email": "unknown@test.com"})
    assert resp.status_code == 200


def test_reset_password_invalid_token(client):
    resp = client.post(f"{API}/auth/reset-password", json={
        "token": "totally-invalid-token",
        "new_password": "NewPass@1234",
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

def test_protected_endpoint_without_token(client):
    resp = client.post(f"{API}/auth/change-password", json={
        "current_password": "x",
        "new_password": "y",
    })
    assert resp.status_code == 401

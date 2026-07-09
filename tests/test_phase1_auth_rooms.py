import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_registration_and_roles():
    # 1. Register a new org "acme" - user "alice" should be admin
    res = client.post(
        "/auth/register",
        json={"org_name": "acme", "username": "alice", "password": "password123"}
    )
    assert res.status_code == 201
    data = res.json()
    assert data["role"] == "admin"
    assert data["username"] == "alice"
    org_id = data["org_id"]
    alice_id = data["user_id"]

    # 2. Register user "bob" to the same org "acme" - should be member
    res2 = client.post(
        "/auth/register",
        json={"org_name": "acme", "username": "bob", "password": "password123"}
    )
    assert res2.status_code == 201
    data2 = res2.json()
    assert data2["role"] == "member"
    assert data2["org_id"] == org_id

    # 3. Register user "bob" again to the same org "acme" - should return 409
    res3 = client.post(
        "/auth/register",
        json={"org_name": "acme", "username": "bob", "password": "newpassword"}
    )
    assert res3.status_code == 409
    assert res3.json()["code"] == "USERNAME_TAKEN"

    # 4. Register user "bob" to a different org "globex" - should succeed
    res4 = client.post(
        "/auth/register",
        json={"org_name": "globex", "username": "bob", "password": "password123"}
    )
    assert res4.status_code == 201
    data4 = res4.json()
    assert data4["role"] == "admin"  # bob is admin of new org globex
    assert data4["org_id"] != org_id


def test_login_and_invalid_credentials():
    # Setup: register user
    client.post(
        "/auth/register",
        json={"org_name": "acme", "username": "alice", "password": "password123"}
    )

    # Correct credentials
    res = client.post(
        "/auth/login",
        json={"org_name": "acme", "username": "alice", "password": "password123"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # Incorrect password
    res = client.post(
        "/auth/login",
        json={"org_name": "acme", "username": "alice", "password": "wrongpassword"}
    )
    assert res.status_code == 401
    assert res.json()["code"] == "INVALID_CREDENTIALS"

    # Non-existent organization
    res = client.post(
        "/auth/login",
        json={"org_name": "nonexistent", "username": "alice", "password": "password123"}
    )
    assert res.status_code == 401
    assert res.json()["code"] == "INVALID_CREDENTIALS"


def test_token_rotation_and_logout():
    # Setup: register & login
    client.post(
        "/auth/register",
        json={"org_name": "acme", "username": "alice", "password": "password123"}
    )
    login_res = client.post(
        "/auth/login",
        json={"org_name": "acme", "username": "alice", "password": "password123"}
    )
    tokens = login_res.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # 1. Refresh using refresh token
    refresh_res = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert refresh_res.status_code == 200
    new_tokens = refresh_res.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    new_access_token = new_tokens["access_token"]

    # 2. Reuse the old refresh token - must return 401
    reuse_res = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert reuse_res.status_code == 401

    # 3. Access endpoint using new access token
    headers = {"Authorization": f"Bearer {new_access_token}"}
    rooms_res = client.get("/rooms", headers=headers)
    assert rooms_res.status_code == 200

    # 4. Logout using new access token
    logout_res = client.post("/auth/logout", headers=headers)
    assert logout_res.status_code == 204

    # 5. Verify the blacklisted access token no longer works
    rooms_res2 = client.get("/rooms", headers=headers)
    assert rooms_res2.status_code == 401


def test_rooms_crud_and_tenancy():
    # Setup Org A (admin = alice, member = bob) and Org B (admin = charlie)
    client.post("/auth/register", json={"org_name": "OrgA", "username": "alice", "password": "password"})
    alice_login = client.post("/auth/login", json={"org_name": "OrgA", "username": "alice", "password": "password"}).json()
    alice_headers = {"Authorization": f"Bearer {alice_login['access_token']}"}

    client.post("/auth/register", json={"org_name": "OrgA", "username": "bob", "password": "password"})
    bob_login = client.post("/auth/login", json={"org_name": "OrgA", "username": "bob", "password": "password"}).json()
    bob_headers = {"Authorization": f"Bearer {bob_login['access_token']}"}

    client.post("/auth/register", json={"org_name": "OrgB", "username": "charlie", "password": "password"})
    charlie_login = client.post("/auth/login", json={"org_name": "OrgB", "username": "charlie", "password": "password"}).json()
    charlie_headers = {"Authorization": f"Bearer {charlie_login['access_token']}"}

    # 1. Admin Alice creates a room
    room_res = client.post(
        "/rooms",
        json={"name": "Conference Room A", "capacity": 10, "hourly_rate_cents": 5000},
        headers=alice_headers
    )
    assert room_res.status_code == 201
    room_id = room_res.json()["id"]

    # 2. Member Bob tries to create a room - must fail with 403 FORBIDDEN
    room_res2 = client.post(
        "/rooms",
        json={"name": "Conference Room B", "capacity": 5, "hourly_rate_cents": 3000},
        headers=bob_headers
    )
    assert room_res2.status_code == 403
    assert room_res2.json()["code"] == "FORBIDDEN"

    # 3. List rooms in OrgA (Alice should see "Conference Room A")
    rooms_a = client.get("/rooms", headers=alice_headers).json()
    assert len(rooms_a) == 1
    assert rooms_a[0]["name"] == "Conference Room A"

    # Bob should also see "Conference Room A" (read is allowed for organization members)
    rooms_bob = client.get("/rooms", headers=bob_headers).json()
    assert len(rooms_bob) == 1
    assert rooms_bob[0]["name"] == "Conference Room A"

    # Charlie (OrgB) should see 0 rooms
    rooms_b = client.get("/rooms", headers=charlie_headers).json()
    assert len(rooms_b) == 0

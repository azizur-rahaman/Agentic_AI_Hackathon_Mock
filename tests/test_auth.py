"""Tests for /auth/register and /auth/login endpoints."""


def test_register_success(client):
    res = client.post("/auth/register", json={"username": "alice", "password": "pass123"})
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == "alice"
    assert "id" in data


def test_register_duplicate_username(client):
    client.post("/auth/register", json={"username": "alice", "password": "pass123"})
    res = client.post("/auth/register", json={"username": "alice", "password": "different"})
    assert res.status_code == 400
    assert "already registered" in res.json()["detail"]


def test_login_success(client):
    client.post("/auth/register", json={"username": "alice", "password": "pass123"})
    res = client.post("/auth/login", data={"username": "alice", "password": "pass123"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client):
    client.post("/auth/register", json={"username": "alice", "password": "pass123"})
    res = client.post("/auth/login", data={"username": "alice", "password": "wrongpass"})
    assert res.status_code == 401


def test_login_unknown_user(client):
    res = client.post("/auth/login", data={"username": "nobody", "password": "pass"})
    assert res.status_code == 401


def test_protected_route_without_token(client):
    res = client.get("/todos")
    assert res.status_code == 401


def test_protected_route_with_invalid_token(client):
    res = client.get("/todos", headers={"Authorization": "Bearer invalidtoken"})
    assert res.status_code == 401


def test_health_endpoint(client):
    """main.py:113 — /health should always return 200."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_token_valid_but_user_deleted(client, auth_headers, db_session):
    """auth.py:61 — a valid token must be rejected if the user no longer exists."""
    from app import models

    user = db_session.query(models.User).filter(models.User.username == "testuser").first()
    db_session.delete(user)
    db_session.commit()

    res = client.get("/todos", headers=auth_headers)
    assert res.status_code == 401


def test_token_with_no_sub_claim(client):
    """auth.py:55 — a valid JWT that has no 'sub' field must be rejected."""
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.auth import SECRET_KEY, ALGORITHM

    # Craft a properly signed token but deliberately omit the 'sub' field
    token = jwt.encode(
        {"exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    res = client.get("/todos", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_get_db_generator():
    """database.py:14-18 — directly unit-test the real get_db() generator."""
    from app.database import get_db

    gen = get_db()
    db = next(gen)          # runs up to yield — opens connection
    assert db is not None
    try:
        next(gen)           # runs finally block — closes connection
    except StopIteration:
        pass                # expected — generator is exhausted

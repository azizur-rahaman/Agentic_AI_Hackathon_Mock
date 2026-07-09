"""Tests for /todos CRUD endpoints."""


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_token(client, username="bob", password="pass123"):
    client.post("/auth/register", json={"username": username, "password": password})
    res = client.post("/auth/login", data={"username": username, "password": password})
    return res.json()["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── Create ───────────────────────────────────────────────────────────────────

def test_create_todo_minimal(client, auth_headers):
    res = client.post("/todos", json={"title": "Buy milk"}, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Buy milk"
    assert data["priority"] == "medium"   # default
    assert data["description"] is None
    assert data["deadline"] is None


def test_create_todo_full(client, auth_headers):
    payload = {
        "title": "Gym",
        "description": "Leg day",
        "deadline": "2026-07-10T18:30:00",
        "priority": "high",
    }
    res = client.post("/todos", json=payload, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["priority"] == "high"
    assert data["description"] == "Leg day"


def test_create_todo_requires_auth(client):
    res = client.post("/todos", json={"title": "No auth"})
    assert res.status_code == 401


def test_create_todo_missing_title(client, auth_headers):
    res = client.post("/todos", json={"priority": "low"}, headers=auth_headers)
    assert res.status_code == 422


# ── List ─────────────────────────────────────────────────────────────────────

def test_list_todos_empty(client, auth_headers):
    res = client.get("/todos", headers=auth_headers)
    assert res.status_code == 200
    assert res.json() == []


def test_list_todos_returns_own_only(client):
    """Bug 3 regression: users must only see their own todos."""
    token_a = _make_token(client, "alice", "pass")
    token_b = _make_token(client, "bob", "pass")

    client.post("/todos", json={"title": "Alice task"}, headers=_headers(token_a))
    client.post("/todos", json={"title": "Alice task 2"}, headers=_headers(token_a))

    res = client.get("/todos", headers=_headers(token_b))
    assert res.status_code == 200
    assert res.json() == []   # Bob sees nothing


def test_list_todos_multiple(client, auth_headers):
    client.post("/todos", json={"title": "Task 1"}, headers=auth_headers)
    client.post("/todos", json={"title": "Task 2"}, headers=auth_headers)
    res = client.get("/todos", headers=auth_headers)
    assert len(res.json()) == 2


# ── Get single ───────────────────────────────────────────────────────────────

def test_get_todo(client, auth_headers):
    todo_id = client.post("/todos", json={"title": "Read book"}, headers=auth_headers).json()["id"]
    res = client.get(f"/todos/{todo_id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["title"] == "Read book"


def test_get_todo_not_found(client, auth_headers):
    res = client.get("/todos/9999", headers=auth_headers)
    assert res.status_code == 404


def test_get_todo_belongs_to_other_user(client):
    token_a = _make_token(client, "alice", "pass")
    token_b = _make_token(client, "bob", "pass")
    todo_id = client.post("/todos", json={"title": "Alice secret"}, headers=_headers(token_a)).json()["id"]
    res = client.get(f"/todos/{todo_id}", headers=_headers(token_b))
    assert res.status_code == 404   # Bob cannot see Alice's todo


# ── Update ───────────────────────────────────────────────────────────────────

def test_update_todo_partial(client, auth_headers):
    """Bug 2 regression: partial PUT must not wipe unset fields."""
    todo_id = client.post(
        "/todos",
        json={"title": "Old title", "priority": "high", "description": "Keep me"},
        headers=auth_headers,
    ).json()["id"]

    res = client.put(f"/todos/{todo_id}", json={"title": "New title"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "New title"
    assert data["priority"] == "high"         # must be preserved
    assert data["description"] == "Keep me"   # must be preserved


def test_update_todo_not_found(client, auth_headers):
    res = client.put("/todos/9999", json={"title": "x"}, headers=auth_headers)
    assert res.status_code == 404


def test_update_todo_belongs_to_other_user(client):
    token_a = _make_token(client, "alice", "pass")
    token_b = _make_token(client, "bob", "pass")
    todo_id = client.post("/todos", json={"title": "Alice task"}, headers=_headers(token_a)).json()["id"]
    res = client.put(f"/todos/{todo_id}", json={"title": "Hijacked"}, headers=_headers(token_b))
    assert res.status_code == 404


# ── Delete ───────────────────────────────────────────────────────────────────

def test_delete_todo(client, auth_headers):
    todo_id = client.post("/todos", json={"title": "Temp"}, headers=auth_headers).json()["id"]
    res = client.delete(f"/todos/{todo_id}", headers=auth_headers)
    assert res.status_code == 204
    assert client.get(f"/todos/{todo_id}", headers=auth_headers).status_code == 404


def test_delete_todo_not_found(client, auth_headers):
    res = client.delete("/todos/9999", headers=auth_headers)
    assert res.status_code == 404


def test_delete_todo_belongs_to_other_user(client):
    token_a = _make_token(client, "alice", "pass")
    token_b = _make_token(client, "bob", "pass")
    todo_id = client.post("/todos", json={"title": "Alice task"}, headers=_headers(token_a)).json()["id"]
    res = client.delete(f"/todos/{todo_id}", headers=_headers(token_b))
    assert res.status_code == 404

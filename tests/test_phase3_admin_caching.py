import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app
from app import cache, models
from app.database import get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_system():
    # Clear cache before each test
    cache.invalidate_all_cache()


def test_admin_usage_report_and_export():
    # Setup: Register admin and user
    client.post("/auth/register", json={"org_name": "OrgA", "username": "alice", "password": "password"})
    alice_login = client.post("/auth/login", json={"org_name": "OrgA", "username": "alice", "password": "password"}).json()
    alice_headers = {"Authorization": f"Bearer {alice_login['access_token']}"}

    client.post("/auth/register", json={"org_name": "OrgA", "username": "bob", "password": "password"})
    bob_login = client.post("/auth/login", json={"org_name": "OrgA", "username": "bob", "password": "password"}).json()
    bob_headers = {"Authorization": f"Bearer {bob_login['access_token']}"}

    # Setup rooms
    r1 = client.post("/rooms", json={"name": "Conference 1", "capacity": 10, "hourly_rate_cents": 1000}, headers=alice_headers).json()["id"]
    r2 = client.post("/rooms", json={"name": "Conference 2", "capacity": 5, "hourly_rate_cents": 2000}, headers=alice_headers).json()["id"]

    # Book room 1 (Alice)
    base_time = (datetime.now(timezone.utc) + timedelta(hours=5)).replace(minute=0, second=0, microsecond=0)
    client.post("/bookings", json={"room_id": r1, "start_time": base_time.isoformat(), "end_time": (base_time + timedelta(hours=2)).isoformat()}, headers=alice_headers)

    # 1. Fetch Admin Usage Report
    from_param = (base_time - timedelta(hours=1)).isoformat()
    to_param = (base_time + timedelta(hours=3)).isoformat()
    
    report_res = client.get("/admin/usage-report", params={"from": from_param, "to": to_param}, headers=alice_headers)
    if report_res.status_code != 200:
        print("ERROR RESPONSE:", report_res.json())
    assert report_res.status_code == 200
    report = report_res.json()
    assert "from" in report
    assert "to" in report
    
    rooms_list = report["rooms"]
    assert len(rooms_list) == 2
    
    r1_data = next(r for r in rooms_list if r["room_id"] == r1)
    r2_data = next(r for r in rooms_list if r["room_id"] == r2)
    
    assert r1_data["confirmed_bookings"] == 1
    assert r1_data["revenue_cents"] == 2000
    assert r2_data["confirmed_bookings"] == 0
    assert r2_data["revenue_cents"] == 0

    # 2. Member Bob tries to fetch report -> 403 Forbidden
    report_res2 = client.get(f"/admin/usage-report?from={from_param}&to={to_param}", headers=bob_headers)
    assert report_res2.status_code == 403

    # 3. CSV Export
    export_res = client.get("/admin/export", headers=alice_headers)
    assert export_res.status_code == 200
    assert export_res.headers["Content-Type"].startswith("text/csv")
    csv_text = export_res.text
    
    # Assert header exactly
    lines = csv_text.strip().split("\r\n")
    assert lines[0] == "id,reference code,room id,user id, start time, end time,status,price cents"
    assert len(lines) == 2 # 1 header + 1 data row


def test_room_stats_availability_and_caching(db_session):
    client.post("/auth/register", json={"org_name": "OrgB", "username": "alice", "password": "password"})
    alice_login = client.post("/auth/login", json={"org_name": "OrgB", "username": "alice", "password": "password"}).json()
    alice_headers = {"Authorization": f"Bearer {alice_login['access_token']}"}
    room_id = client.post("/rooms", json={"name": "Conference B", "capacity": 10, "hourly_rate_cents": 1000}, headers=alice_headers).json()["id"]

    # 1. Availability check (no bookings yet)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    avail_res = client.get(f"/rooms/{room_id}/availability?date={today_str}", headers=alice_headers)
    assert avail_res.status_code == 200
    assert len(avail_res.json()["busy"]) == 0

    # 2. Call stats (starts with 0)
    stats_res = client.get(f"/rooms/{room_id}/stats", headers=alice_headers)
    assert stats_res.status_code == 200
    assert stats_res.json()["total_confirmed_bookings"] == 0

    # 3. Modify DB record directly to simulate cache persistence bypass
    # Retrieve the stats cache to confirm it's now populated
    assert cache.get_cached_stats(room_id) is not None
    
    # Directly update stats cache in-memory to verify it's utilized on next call
    cache.set_cached_stats(room_id, {"room_id": room_id, "total_confirmed_bookings": 99, "total_revenue_cents": 9900})
    
    stats_res2 = client.get(f"/rooms/{room_id}/stats", headers=alice_headers)
    assert stats_res2.json()["total_confirmed_bookings"] == 99  # Hits cache

    # 4. Make a booking to trigger write-through cache invalidation
    base_time = (datetime.now(timezone.utc) + timedelta(hours=4)).replace(minute=0, second=0, microsecond=0)
    client.post("/bookings", json={"room_id": room_id, "start_time": base_time.isoformat(), "end_time": (base_time + timedelta(hours=1)).isoformat()}, headers=alice_headers)

    # 5. Check stats again. Cache was invalidated, so it must return 1 booking from the DB
    stats_res3 = client.get(f"/rooms/{room_id}/stats", headers=alice_headers)
    assert stats_res3.json()["total_confirmed_bookings"] == 1
    assert stats_res3.json()["total_revenue_cents"] == 1000

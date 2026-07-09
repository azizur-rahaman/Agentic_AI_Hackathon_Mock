import pytest
import threading
import time
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.services import rate_limiter

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    rate_limiter.booking_requests.clear()


def test_datetime_and_window_validations():
    # Setup Org, Admin & Member
    client.post("/auth/register", json={"org_name": "OrgA", "username": "alice", "password": "password"})
    alice_login = client.post("/auth/login", json={"org_name": "OrgA", "username": "alice", "password": "password"}).json()
    alice_headers = {"Authorization": f"Bearer {alice_login['access_token']}"}

    room_res = client.post(
        "/rooms",
        json={"name": "Conference Room 1", "capacity": 10, "hourly_rate_cents": 5000},
        headers=alice_headers
    )
    room_id = room_res.json()["id"]

    # 1. Past start time -> 400 INVALID_BOOKING_WINDOW
    past_start = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    past_end = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    res = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": past_start, "end_time": past_end},
        headers=alice_headers
    )
    assert res.status_code == 400
    assert res.json()["code"] == "INVALID_BOOKING_WINDOW"

    # 2. Non-whole hour duration -> 400 INVALID_BOOKING_WINDOW
    future_start = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    invalid_end = future_start + timedelta(minutes=90)
    res2 = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": future_start.isoformat(), "end_time": invalid_end.isoformat()},
        headers=alice_headers
    )
    assert res2.status_code == 400
    assert res2.json()["code"] == "INVALID_BOOKING_WINDOW"

    # 3. Duration < 1 hour -> 400 INVALID_BOOKING_WINDOW
    invalid_end2 = future_start + timedelta(minutes=30)
    res3 = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": future_start.isoformat(), "end_time": invalid_end2.isoformat()},
        headers=alice_headers
    )
    assert res3.status_code == 400

    # 4. Duration > 8 hours -> 400 INVALID_BOOKING_WINDOW
    invalid_end3 = future_start + timedelta(hours=9)
    res4 = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": future_start.isoformat(), "end_time": invalid_end3.isoformat()},
        headers=alice_headers
    )
    assert res4.status_code == 400


def test_double_booking_prevention():
    client.post("/auth/register", json={"org_name": "OrgA", "username": "alice", "password": "password"})
    alice_login = client.post("/auth/login", json={"org_name": "OrgA", "username": "alice", "password": "password"}).json()
    alice_headers = {"Authorization": f"Bearer {alice_login['access_token']}"}

    room_res = client.post(
        "/rooms",
        json={"name": "Conference Room 1", "capacity": 10, "hourly_rate_cents": 5000},
        headers=alice_headers
    )
    room_id = room_res.json()["id"]

    # Book 14:00 to 16:00
    start = (datetime.now(timezone.utc) + timedelta(hours=5)).replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=2)

    res = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": start.isoformat(), "end_time": end.isoformat()},
        headers=alice_headers
    )
    assert res.status_code == 201

    # Try to book overlapping 13:00 to 15:00 -> Conflict 409
    overlap_start1 = start - timedelta(hours=1)
    overlap_end1 = start + timedelta(hours=1)
    res1 = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": overlap_start1.isoformat(), "end_time": overlap_end1.isoformat()},
        headers=alice_headers
    )
    assert res1.status_code == 409
    assert res1.json()["code"] == "ROOM_CONFLICT"

    # Try to book overlapping 15:00 to 17:00 -> Conflict 409
    overlap_start2 = start + timedelta(hours=1)
    overlap_end2 = end + timedelta(hours=1)
    res2 = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": overlap_start2.isoformat(), "end_time": overlap_end2.isoformat()},
        headers=alice_headers
    )
    assert res2.status_code == 409

    # Book back-to-back 16:00 to 17:00 -> Should pass
    res3 = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": end.isoformat(), "end_time": (end + timedelta(hours=1)).isoformat()},
        headers=alice_headers
    )
    assert res3.status_code == 201


def test_booking_quota_and_cancellation():
    client.post("/auth/register", json={"org_name": "OrgA", "username": "alice", "password": "password"})
    alice_login = client.post("/auth/login", json={"org_name": "OrgA", "username": "alice", "password": "password"}).json()
    alice_headers = {"Authorization": f"Bearer {alice_login['access_token']}"}

    client.post("/auth/register", json={"org_name": "OrgA", "username": "bob", "password": "password"})
    bob_login = client.post("/auth/login", json={"org_name": "OrgA", "username": "bob", "password": "password"}).json()
    bob_headers = {"Authorization": f"Bearer {bob_login['access_token']}"}

    # Setup rooms
    room1 = client.post("/rooms", json={"name": "R1", "capacity": 5, "hourly_rate_cents": 1000}, headers=alice_headers).json()["id"]
    room2 = client.post("/rooms", json={"name": "R2", "capacity": 5, "hourly_rate_cents": 1000}, headers=alice_headers).json()["id"]
    room3 = client.post("/rooms", json={"name": "R3", "capacity": 5, "hourly_rate_cents": 1000}, headers=alice_headers).json()["id"]
    room4 = client.post("/rooms", json={"name": "R4", "capacity": 5, "hourly_rate_cents": 1000}, headers=alice_headers).json()["id"]

    # Bob (member) makes 3 bookings in next 24 hours
    base_time = (datetime.now(timezone.utc) + timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
    
    b1 = client.post("/bookings", json={"room_id": room1, "start_time": base_time.isoformat(), "end_time": (base_time + timedelta(hours=1)).isoformat()}, headers=bob_headers)
    assert b1.status_code == 201
    booking_id = b1.json()["id"]

    b2 = client.post("/bookings", json={"room_id": room2, "start_time": base_time.isoformat(), "end_time": (base_time + timedelta(hours=1)).isoformat()}, headers=bob_headers)
    assert b2.status_code == 201

    b3 = client.post("/bookings", json={"room_id": room3, "start_time": base_time.isoformat(), "end_time": (base_time + timedelta(hours=1)).isoformat()}, headers=bob_headers)
    assert b3.status_code == 201

    # 4th booking in same window -> 409 QUOTA_EXCEEDED
    b4 = client.post("/bookings", json={"room_id": room4, "start_time": base_time.isoformat(), "end_time": (base_time + timedelta(hours=1)).isoformat()}, headers=bob_headers)
    assert b4.status_code == 409
    assert b4.json()["code"] == "QUOTA_EXCEEDED"

    # Alice (admin) tries to book -> should succeed (exempt from quota)
    b_admin = client.post("/bookings", json={"room_id": room4, "start_time": base_time.isoformat(), "end_time": (base_time + timedelta(hours=1)).isoformat()}, headers=alice_headers)
    assert b_admin.status_code == 201

    # Bob cancels his first booking (under 24h notice -> 0% refund)
    cancel_res = client.post(f"/bookings/{booking_id}/cancel", headers=bob_headers)
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["refund_percent"] == 0
    assert cancel_data["refund_amount_cents"] == 0

    # Try cancelling again -> 409 ALREADY_CANCELLED
    cancel_res2 = client.post(f"/bookings/{booking_id}/cancel", headers=bob_headers)
    assert cancel_res2.status_code == 409
    assert cancel_res2.json()["code"] == "ALREADY_CANCELLED"


def test_refund_notice_tiers():
    client.post("/auth/register", json={"org_name": "OrgA", "username": "alice", "password": "password"})
    alice_login = client.post("/auth/login", json={"org_name": "OrgA", "username": "alice", "password": "password"}).json()
    alice_headers = {"Authorization": f"Bearer {alice_login['access_token']}"}
    room_id = client.post("/rooms", json={"name": "R1", "capacity": 5, "hourly_rate_cents": 1235}, headers=alice_headers).json()["id"]

    # Tier 1: Notice >= 48 hours -> 100% refund
    t1_start = (datetime.now(timezone.utc) + timedelta(hours=50)).replace(minute=0, second=0, microsecond=0)
    t1_end = t1_start + timedelta(hours=2) # 2 hours * 1235 = 2470 cents
    b1 = client.post("/bookings", json={"room_id": room_id, "start_time": t1_start.isoformat(), "end_time": t1_end.isoformat()}, headers=alice_headers).json()
    
    c1 = client.post(f"/bookings/{b1['id']}/cancel", headers=alice_headers).json()
    assert c1["refund_percent"] == 100
    assert c1["refund_amount_cents"] == 2470

    # Tier 2: 24 <= Notice < 48 hours -> 50% refund (with rounding half-up)
    t2_start = (datetime.now(timezone.utc) + timedelta(hours=30)).replace(minute=0, second=0, microsecond=0)
    t2_end = t2_start + timedelta(hours=1) # 1 hour * 1235 = 1235 cents. 50% = 617.5 cents -> rounds to 618
    b2 = client.post("/bookings", json={"room_id": room_id, "start_time": t2_start.isoformat(), "end_time": t2_end.isoformat()}, headers=alice_headers).json()
    
    c2 = client.post(f"/bookings/{b2['id']}/cancel", headers=alice_headers).json()
    assert c2["refund_percent"] == 50
    assert c2["refund_amount_cents"] == 618


def test_rate_limiter():
    client.post("/auth/register", json={"org_name": "OrgRate", "username": "user1", "password": "password"})
    login = client.post("/auth/login", json={"org_name": "OrgRate", "username": "user1", "password": "password"}).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    # Reset/Mock request history for user1 to simulate 20 requests
    from app.services import rate_limiter
    rate_limiter.booking_requests.clear()

    # Call 20 times (all will fail room existence, but rate limiter records all attempts)
    for _ in range(20):
        client.post("/bookings", json={"room_id": 9999, "start_time": "2026-10-10T10:00:00Z", "end_time": "2026-10-10T11:00:00Z"}, headers=headers)

    # 21st call should trigger 429
    res = client.post("/bookings", json={"room_id": 9999, "start_time": "2026-10-10T10:00:00Z", "end_time": "2026-10-10T11:00:00Z"}, headers=headers)
    assert res.status_code == 429
    assert res.json()["code"] == "RATE_LIMITED"


def test_concurrent_double_bookings():
    # Setup
    client.post("/auth/register", json={"org_name": "OrgLock", "username": "alice", "password": "password"})
    alice_login = client.post("/auth/login", json={"org_name": "OrgLock", "username": "alice", "password": "password"}).json()
    alice_headers = {"Authorization": f"Bearer {alice_login['access_token']}"}
    room_id = client.post("/rooms", json={"name": "R1", "capacity": 5, "hourly_rate_cents": 1000}, headers=alice_headers).json()["id"]

    start = (datetime.now(timezone.utc) + timedelta(hours=10)).replace(minute=0, second=0, microsecond=0).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=11)).replace(minute=0, second=0, microsecond=0).isoformat()

    results = []

    def perform_booking():
        # Clean local client per thread
        th_client = TestClient(app)
        res = th_client.post(
            "/bookings",
            json={"room_id": room_id, "start_time": start, "end_time": end},
            headers=alice_headers
        )
        results.append(res)

    threads = [threading.Thread(target=perform_booking) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Assert exactly 1 succeeded (201) and others failed (409)
    success = [r for r in results if r.status_code == 201]
    conflict = [r for r in results if r.status_code == 409]

    assert len(success) == 1
    assert len(conflict) == 4

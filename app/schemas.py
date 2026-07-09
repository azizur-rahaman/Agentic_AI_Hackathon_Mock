from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    org_name: str
    username: str
    password: str


class RegisterResponse(BaseModel):
    user_id: int
    org_id: int
    username: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    org_name: str
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class RoomCreate(BaseModel):
    name: str
    capacity: int
    hourly_rate_cents: int


class RoomOut(BaseModel):
    id: int
    org_id: int
    name: str
    capacity: int
    hourly_rate_cents: int

    model_config = ConfigDict(from_attributes=True)


class BookingCreate(BaseModel):
    room_id: int
    start_time: datetime
    end_time: datetime


class BookingOut(BaseModel):
    id: int
    reference_code: str
    room_id: int
    user_id: int
    start_time: datetime
    end_time: datetime
    status: str
    price_cents: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedBookings(BaseModel):
    items: List[BookingOut]
    page: int
    limit: int
    total: int


class RefundLogOut(BaseModel):
    amount_cents: int
    status: str
    processed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingDetailOut(BookingOut):
    refunds: List[RefundLogOut]


class CancelResponse(BaseModel):
    id: int
    status: str = "cancelled"
    refund_percent: int
    refund_amount_cents: int


# Availability & stats
class BusyInterval(BaseModel):
    start_time: datetime
    end_time: datetime


class AvailabilityOut(BaseModel):
    room_id: int
    date: str
    busy: List[BusyInterval]


class StatsOut(BaseModel):
    room_id: int
    total_confirmed_bookings: int
    total_revenue_cents: int


# Usage Report
class UsageReportRoom(BaseModel):
    room_id: int
    room_name: str
    confirmed_bookings: int
    revenue_cents: int


class UsageReportOut(BaseModel):
    from_date: datetime = Field(..., alias="from")
    to_date: datetime = Field(..., alias="to")
    rooms: List[UsageReportRoom]

    model_config = ConfigDict(populate_by_name=True)

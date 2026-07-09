import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class Role(str, enum.Enum):
    admin = "admin"
    member = "member"


class BookingStatus(str, enum.Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"


class RefundStatus(str, enum.Enum):
    processed = "processed"
    failed = "failed"


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

    users = relationship("User", back_populates="org", cascade="all, delete-orphan")
    rooms = relationship("Room", back_populates="org", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    username = Column(String, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="member", nullable=False)  # "admin" or "member"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    org = relationship("Organization", back_populates="users")
    bookings = relationship("Booking", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("org_id", "username", name="uq_user_org_username"),
    )


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)
    capacity = Column(Integer, nullable=False)
    hourly_rate_cents = Column(Integer, nullable=False)

    org = relationship("Organization", back_populates="rooms")
    bookings = relationship("Booking", back_populates="room", cascade="all, delete-orphan")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String, default="confirmed", nullable=False)  # "confirmed" or "cancelled"
    reference_code = Column(String, unique=True, index=True, nullable=False)
    price_cents = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    room = relationship("Room", back_populates="bookings")
    user = relationship("User", back_populates="bookings")
    refunds = relationship("RefundLog", back_populates="booking", cascade="all, delete-orphan")


class RefundLog(Base):
    __tablename__ = "refund_logs"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    status = Column(String, nullable=False)  # "processed" or "failed"
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    booking = relationship("Booking", back_populates="refunds")

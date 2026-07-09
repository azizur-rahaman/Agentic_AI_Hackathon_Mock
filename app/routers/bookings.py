import threading
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from typing import List

from .. import auth, models, schemas, timeutils
from ..database import get_db
from ..services import rate_limiter, ref_codes, refunds
from ..errors import (
    RoomConflictException,
    QuotaExceededException,
    AlreadyCancelledException,
    BookingNotFoundException,
    RoomNotFoundException,
    InvalidBookingWindowException
)

router = APIRouter(prefix="/bookings", tags=["bookings"])
booking_lock = threading.Lock()


@router.post("", response_model=schemas.BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    req: schemas.BookingCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Rate limiter check (all requests count, so this runs first)
    rate_limiter.check_rate_limit(current_user.id)

    # 2. Parse and normalize incoming datetimes to UTC naive
    start_time = timeutils.normalize_datetime(req.start_time)
    end_time = timeutils.normalize_datetime(req.end_time)

    # 3. Booking window checks
    if end_time <= start_time:
        raise InvalidBookingWindowException("end_time must be strictly after start_time")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if start_time <= now:
        raise InvalidBookingWindowException("start_time must be strictly in the future")

    duration_seconds = (end_time - start_time).total_seconds()
    duration_hours = duration_seconds / 3600.0

    # Must be a whole number of hours
    if not duration_hours.is_integer():
        raise InvalidBookingWindowException("duration must be a whole number of hours")

    duration_hours = int(duration_hours)
    if duration_hours < 1 or duration_hours > 8:
        raise InvalidBookingWindowException("duration must be between 1 and 8 hours")

    # 4. Check room existence and multi-tenant visibility
    room = db.query(models.Room).filter(
        models.Room.id == req.room_id,
        models.Room.org_id == current_user.org_id
    ).first()
    if not room:
        raise RoomNotFoundException()

    # 5. Lock critical section for overlapping bookings & quota checks
    with booking_lock:
        # Check overlapping confirmed bookings
        overlap = db.query(models.Booking).filter(
            models.Booking.room_id == req.room_id,
            models.Booking.status == "confirmed",
            models.Booking.start_time < end_time,
            models.Booking.end_time > start_time
        ).first()

        if overlap:
            raise RoomConflictException()

        # Check quota for members (admins are exempt)
        if current_user.role != "admin":
            # Count confirmed bookings starting in (now, now + 24h]
            end_window = now + timedelta(hours=24)
            active_bookings_count = db.query(models.Booking).join(models.Room).filter(
                models.Booking.user_id == current_user.id,
                models.Booking.status == "confirmed",
                models.Booking.start_time > now,
                models.Booking.start_time <= end_window
            ).count()

            if active_bookings_count >= 3:
                raise QuotaExceededException()

        # Calculate price and generate code
        price_cents = room.hourly_rate_cents * duration_hours
        ref_code = ref_codes.generate_unique_reference_code(db)

        booking = models.Booking(
            room_id=req.room_id,
            user_id=current_user.id,
            start_time=start_time,
            end_time=end_time,
            status="confirmed",
            reference_code=ref_code,
            price_cents=price_cents,
            created_at=datetime.utcnow()
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

    return booking


@router.get("", response_model=schemas.PaginatedBookings)
def list_bookings(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role == "admin":
        query = db.query(models.Booking).join(models.Room).filter(
            models.Room.org_id == current_user.org_id
        )
    else:
        query = db.query(models.Booking).filter(
            models.Booking.user_id == current_user.id
        )

    query = query.order_by(models.Booking.start_time.asc(), models.Booking.id.asc())

    total = query.count()
    offset = (page - 1) * limit
    items = query.offset(offset).limit(limit).all()

    return schemas.PaginatedBookings(
        items=items,
        page=page,
        limit=limit,
        total=total
    )


@router.get("/{id}", response_model=schemas.BookingDetailOut)
def get_booking(
    id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(models.Booking).join(models.Room).filter(
        models.Booking.id == id,
        models.Room.org_id == current_user.org_id
    ).first()

    if not booking:
        raise BookingNotFoundException()

    # Visibility rules: members can only read their own bookings
    if current_user.role != "admin" and booking.user_id != current_user.id:
        raise BookingNotFoundException()

    return booking


@router.post("/{id}/cancel", response_model=schemas.CancelResponse)
def cancel_booking(
    id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # Lock critical section for status modification & refund logging
    with booking_lock:
        booking = db.query(models.Booking).join(models.Room).filter(
            models.Booking.id == id,
            models.Room.org_id == current_user.org_id
        ).first()

        if not booking:
            raise BookingNotFoundException()

        # Cancellation visibility check
        if current_user.role != "admin" and booking.user_id != current_user.id:
            raise BookingNotFoundException()

        # Check if already cancelled
        if booking.status == "cancelled":
            raise AlreadyCancelledException()

        # Calculate refund
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        refund_percent, refund_amount_cents = refunds.calculate_refund(
            booking.start_time, now, booking.price_cents
        )

        # Mark cancelled
        booking.status = "cancelled"

        # Create RefundLog entry
        refund_log = models.RefundLog(
            booking_id=booking.id,
            amount_cents=refund_amount_cents,
            status="processed",
            processed_at=now
        )
        db.add(refund_log)
        db.commit()
        db.refresh(booking)

    return schemas.CancelResponse(
        id=booking.id,
        status="cancelled",
        refund_percent=refund_percent,
        refund_amount_cents=refund_amount_cents
    )

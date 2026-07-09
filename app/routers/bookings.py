from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from typing import Optional

from .. import auth, models, schemas
from ..database import get_db
from ..errors import BookingNotFoundException

router = APIRouter(prefix="/bookings", tags=["bookings"])


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

    # Sort ascending by start_time, ties resolved by ascending id
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

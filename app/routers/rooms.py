from datetime import datetime, date
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from .. import auth, models, schemas, cache
from ..database import get_db
from ..errors import RoomNotFoundException

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=List[schemas.RoomOut])
def list_rooms(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    rooms = db.query(models.Room).filter(models.Room.org_id == current_user.org_id).all()
    return rooms


@router.post("", response_model=schemas.RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(
    room_in: schemas.RoomCreate,
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    room = models.Room(
        org_id=current_admin.org_id,
        name=room_in.name,
        capacity=room_in.capacity,
        hourly_rate_cents=room_in.hourly_rate_cents
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@router.get("/{id}/availability", response_model=schemas.AvailabilityOut)
def get_room_availability(
    id: int,
    date_str: str = Query(..., alias="date", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # Check room exists & belongs to org
    room = db.query(models.Room).filter(
        models.Room.id == id,
        models.Room.org_id == current_user.org_id
    ).first()
    if not room:
        raise RoomNotFoundException()

    # Check cache first
    cached = cache.get_cached_availability(id, date_str)
    if cached is not None:
        return cached

    # Parse date range in UTC
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    bookings = db.query(models.Booking).filter(
        models.Booking.room_id == id,
        models.Booking.status == "confirmed",
        models.Booking.start_time >= start_of_day,
        models.Booking.start_time <= end_of_day
    ).order_by(models.Booking.start_time.asc()).all()

    busy = [{"start_time": b.start_time, "end_time": b.end_time} for b in bookings]
    result = {
        "room_id": id,
        "date": date_str,
        "busy": busy
    }

    # Save to cache
    cache.set_cached_availability(id, date_str, result)
    return result


@router.get("/{id}/stats", response_model=schemas.StatsOut)
def get_room_stats(
    id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # Check room exists & belongs to org
    room = db.query(models.Room).filter(
        models.Room.id == id,
        models.Room.org_id == current_user.org_id
    ).first()
    if not room:
        raise RoomNotFoundException()

    # Check cache first
    cached = cache.get_cached_stats(id)
    if cached is not None:
        return cached

    # Query stats
    stats = db.query(
        func.count(models.Booking.id).label("count"),
        func.sum(models.Booking.price_cents).label("revenue")
    ).filter(
        models.Booking.room_id == id,
        models.Booking.status == "confirmed"
    ).first()

    total_bookings = stats.count or 0
    total_revenue = stats.revenue or 0

    result = {
        "room_id": id,
        "total_confirmed_bookings": total_bookings,
        "total_revenue_cents": total_revenue
    }

    # Save to cache
    cache.set_cached_stats(id, result)
    return result

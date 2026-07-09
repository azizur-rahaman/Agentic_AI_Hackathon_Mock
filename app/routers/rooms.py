from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from .. import auth, models, schemas
from ..database import get_db

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

from datetime import datetime
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from .. import auth, models, schemas, timeutils
from ..database import get_db
from ..services import export

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/usage-report", response_model=schemas.UsageReportOut)
def get_usage_report(
    from_param: datetime = Query(..., alias="from"),
    to_param: datetime = Query(..., alias="to"),
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    from_dt = timeutils.normalize_datetime(from_param)
    to_dt = timeutils.normalize_datetime(to_param)

    # Fetch all rooms in organization
    rooms = db.query(models.Room).filter(models.Room.org_id == current_admin.org_id).all()

    rooms_data = []
    for r in rooms:
        stats = db.query(
            func.count(models.Booking.id).label("count"),
            func.sum(models.Booking.price_cents).label("revenue")
        ).filter(
            models.Booking.room_id == r.id,
            models.Booking.status == "confirmed",
            models.Booking.start_time >= from_dt,
            models.Booking.start_time <= to_dt
        ).first()

        rooms_data.append(schemas.UsageReportRoom(
            room_id=r.id,
            room_name=r.name,
            confirmed_bookings=stats.count or 0,
            revenue_cents=stats.revenue or 0
        ))

    return schemas.UsageReportOut(
        from_date=from_dt,
        to_date=to_dt,
        rooms=rooms_data
    )


@router.get("/export")
def export_bookings_csv(
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    # Fetch all bookings for all rooms belonging to the admin's organization
    bookings = db.query(models.Booking).join(models.Room).filter(
        models.Room.org_id == current_admin.org_id
    ).order_by(models.Booking.id.asc()).all()

    csv_content = export.generate_bookings_csv(bookings)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bookings.csv"}
    )

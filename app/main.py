from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import models
from .database import engine
from .errors import CoWorkException
from .routers import auth, rooms, bookings, admin, health

# Create DB tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="CoWork: Multi-Tenant Coworking Space Booking API")


# Exception handler for CoWork domain exceptions
@app.exception_handler(CoWorkException)
def cowork_exception_handler(request: Request, exc: CoWorkException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "code": exc.code
        }
    )


# Include all routers
app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(bookings.router)
app.include_router(admin.router)
app.include_router(health.router)

from fastapi import HTTPException, status

class CoWorkException(HTTPException):
    def __init__(self, status_code: int, detail: str, code: str):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code


class UsernameTakenException(CoWorkException):
    def __init__(self, detail: str = "Username already taken within organization"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail, code="USERNAME_TAKEN")


class InvalidCredentialsException(CoWorkException):
    def __init__(self, detail: str = "Incorrect username or password"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, code="INVALID_CREDENTIALS")


class RoomConflictException(CoWorkException):
    def __init__(self, detail: str = "Room is already booked for this slot"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail, code="ROOM_CONFLICT")


class QuotaExceededException(CoWorkException):
    def __init__(self, detail: str = "Booking quota exceeded for the next 24 hours"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail, code="QUOTA_EXCEEDED")


class RateLimitedException(CoWorkException):
    def __init__(self, detail: str = "Too many requests. Please try again later."):
        super().__init__(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail, code="RATE_LIMITED")


class AlreadyCancelledException(CoWorkException):
    def __init__(self, detail: str = "Booking is already cancelled"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail, code="ALREADY_CANCELLED")


class BookingNotFoundException(CoWorkException):
    def __init__(self, detail: str = "Booking not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail, code="BOOKING_NOT_FOUND")


class RoomNotFoundException(CoWorkException):
    def __init__(self, detail: str = "Room not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail, code="ROOM_NOT_FOUND")


class ForbiddenException(CoWorkException):
    def __init__(self, detail: str = "Access forbidden"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail, code="FORBIDDEN")


class InvalidBookingWindowException(CoWorkException):
    def __init__(self, detail: str = "Invalid booking window: past start, non-whole or out of range duration"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail, code="INVALID_BOOKING_WINDOW")

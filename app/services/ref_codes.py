import secrets
import string
from sqlalchemy.orm import Session
from .. import models


def generate_reference_code() -> str:
    """
    Generates a secure, random 8-character uppercase alphanumeric string.
    """
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def generate_unique_reference_code(db: Session) -> str:
    """
    Generates a reference code and checks the database to guarantee uniqueness.
    """
    for _ in range(10):  # Retry up to 10 times in case of conflict
        ref = generate_reference_code()
        exists = db.query(models.Booking).filter(models.Booking.reference_code == ref).first()
        if not exists:
            return ref
    raise RuntimeError("Failed to generate a unique reference code after multiple attempts")

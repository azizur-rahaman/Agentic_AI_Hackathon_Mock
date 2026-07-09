import decimal
from datetime import datetime, timezone

def round_half_up(amount: float) -> int:
    return int(decimal.Decimal(str(amount)).quantize(decimal.Decimal('1'), rounding=decimal.ROUND_HALF_UP))


def calculate_refund(start_time: datetime, cancellation_time: datetime, price_cents: int) -> tuple[int, int]:
    """
    Given the start_time of the booking, cancellation_time, and price_cents,
    returns a tuple of (refund_percent, refund_amount_cents).
    """
    # Make sure we normalize datetimes to naive UTC for calculation
    st = start_time.replace(tzinfo=None) if start_time.tzinfo else start_time
    ct = cancellation_time.replace(tzinfo=None) if cancellation_time.tzinfo else cancellation_time
    
    notice_hours = (st - ct).total_seconds() / 3600.0

    if notice_hours >= 48.0:
        refund_percent = 100
    elif notice_hours >= 24.0:
        refund_percent = 50
    else:
        refund_percent = 0

    refund_amount_cents = round_half_up(price_cents * (refund_percent / 100.0))
    return refund_percent, refund_amount_cents

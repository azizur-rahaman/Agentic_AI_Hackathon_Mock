from datetime import datetime, timezone


def normalize_datetime(dt: datetime) -> datetime:
    """
    Converts input datetime (naive or aware) to naive UTC datetime.
    - If naive, assumes it is UTC.
    - If aware, converts to UTC and strips tzinfo.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def make_utc_aware(dt: datetime) -> datetime:
    """
    Ensures datetime is timezone-aware and localized to UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

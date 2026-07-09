import time
import threading
from ..errors import RateLimitedException

# dict mapping user_id -> list of float timestamps
booking_requests = {}
rate_limiter_lock = threading.Lock()


def check_rate_limit(user_id: int):
    """
    Checks if the user has made more than 20 requests in the last 60 seconds.
    All requests (successful, failed, and even rate-limited ones) count.
    Raises RateLimitedException if limit is exceeded.
    """
    now = time.time()
    with rate_limiter_lock:
        user_requests = booking_requests.setdefault(user_id, [])
        # Keep only requests within the last 60 seconds
        user_requests[:] = [t for t in user_requests if now - t <= 60.0]
        
        if len(user_requests) >= 20:
            user_requests.append(now)
            raise RateLimitedException()
        
        user_requests.append(now)

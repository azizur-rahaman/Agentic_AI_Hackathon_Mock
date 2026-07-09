import threading

cache_lock = threading.Lock()

# Cache storage
# (room_id, date_str) -> dict
availability_cache = {}

# room_id -> dict
stats_cache = {}


def get_cached_availability(room_id: int, date_str: str) -> dict:
    with cache_lock:
        return availability_cache.get((room_id, date_str))


def set_cached_availability(room_id: int, date_str: str, data: dict):
    with cache_lock:
        availability_cache[(room_id, date_str)] = data


def get_cached_stats(room_id: int) -> dict:
    with cache_lock:
        return stats_cache.get(room_id)


def set_cached_stats(room_id: int, data: dict):
    with cache_lock:
        stats_cache[room_id] = data


def invalidate_room_cache(room_id: int):
    """
    Clears stats and availability cache for a specific room.
    """
    with cache_lock:
        stats_cache.pop(room_id, None)
        # Identify all keys for this room_id in availability
        keys_to_remove = [key for key in availability_cache if key[0] == room_id]
        for key in keys_to_remove:
            availability_cache.pop(key, None)


def invalidate_all_cache():
    """
    Clears all cache entries.
    """
    with cache_lock:
        availability_cache.clear()
        stats_cache.clear()

"""One in-flight agent run per user (per process).

In-memory, so it is only exact while gunicorn runs a single worker. Move it to
Redis before adding workers.
"""

import threading

_active: set[str] = set()
_lock = threading.Lock()


def try_acquire(user_id: str) -> bool:
    with _lock:
        if user_id in _active:
            return False
        _active.add(user_id)
        return True


def release(user_id: str) -> None:
    with _lock:
        _active.discard(user_id)

import time
from collections import defaultdict, deque

from fastapi import HTTPException

from ..config import settings


class LoginLimiter:
    """In-memory failed-login counter per key (e.g. "ip|email").

    Fine for a single server process. With several instances, back this with Redis or a database table.
    """

    def __init__(self):
        self._fails: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque:
        window = settings.login_window_minutes * 60
        q = self._fails[key]
        while q and time.monotonic() - q[0] > window:
            q.popleft()
        if not q:
            self._fails.pop(key, None)
        return q

    def check(self, key: str) -> None:
        q = self._prune(key)
        if len(q) >= settings.login_max_failures:
            wait = int(settings.login_window_minutes * 60 - (time.monotonic() - q[0])) + 1
            raise HTTPException(429, f"Too many sign-in attempts. Try again in {max(1, wait // 60)} minute(s).",
                                headers={"Retry-After": str(wait)})

    def fail(self, key: str) -> None:
        self._fails[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)

    def reset_all(self) -> None:
        self._fails.clear()


login_limiter = LoginLimiter()

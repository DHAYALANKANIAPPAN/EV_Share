import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException

from ..config import settings

logger = logging.getLogger(__name__)


class MemoryLoginLimiter:
    """In-memory failed-login counter per key (e.g. "ip|email"). Single-process development only."""

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


class RedisLoginLimiter:
    """Redis-backed failed-login counter using a sliding window in a sorted set (ZSET).

    Safe across multiple worker processes, server restarts, and horizontally scaled instances.
    """

    def __init__(self, client=None, prefix: str = "evshare:ratelimit:login:"):
        self._client = client
        self._prefix = prefix

    @property
    def client(self):
        if self._client is None:
            import redis
            self._client = redis.from_url(settings.redis_url, decode_responses=True)
        return self._client

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def check(self, key: str) -> None:
        r_key = self._key(key)
        now = time.time()
        window = settings.login_window_minutes * 60
        try:
            pipe = self.client.pipeline()
            pipe.zremrangebyscore(r_key, 0, now - window)
            pipe.zrange(r_key, 0, -1, withscores=True)
            _, entries = pipe.execute()
        except Exception as e:
            logger.warning("Redis rate limit check error: %s", e)
            return

        if len(entries) >= settings.login_max_failures:
            oldest_ts = float(entries[0][1])
            wait = int(window - (now - oldest_ts)) + 1
            raise HTTPException(
                429,
                f"Too many sign-in attempts. Try again in {max(1, wait // 60)} minute(s).",
                headers={"Retry-After": str(max(1, wait))},
            )

    def fail(self, key: str) -> None:
        r_key = self._key(key)
        now = time.time()
        window = settings.login_window_minutes * 60
        member = f"{now}:{uuid.uuid4().hex[:8]}"
        try:
            pipe = self.client.pipeline()
            pipe.zadd(r_key, {member: now})
            pipe.expire(r_key, int(window) + 60)
            pipe.execute()
        except Exception as e:
            logger.warning("Redis rate limit fail recording error: %s", e)

    def reset(self, key: str) -> None:
        try:
            self.client.delete(self._key(key))
        except Exception as e:
            logger.warning("Redis rate limit reset error: %s", e)

    def reset_all(self) -> None:
        try:
            cursor = 0
            while True:
                cursor, keys = self.client.scan(cursor=cursor, match=f"{self._prefix}*", count=100)
                if keys:
                    self.client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("Redis rate limit reset_all error: %s", e)


class LoginLimiter:
    """Delegating limiter that dynamically selects Redis or Memory based on configuration."""

    def __init__(self):
        self._memory = MemoryLoginLimiter()
        self._redis = None

    @property
    def backend(self):
        if settings.ratelimit_backend == "redis" or (settings.redis_url and settings.ratelimit_backend != "memory"):
            if self._redis is None:
                self._redis = RedisLoginLimiter()
            return self._redis
        return self._memory

    def check(self, key: str) -> None:
        self.backend.check(key)

    def fail(self, key: str) -> None:
        self.backend.fail(key)

    def reset(self, key: str) -> None:
        self.backend.reset(key)

    def reset_all(self) -> None:
        if self._redis is not None:
            self._redis.reset_all()
        self._memory.reset_all()


login_limiter = LoginLimiter()

import time
import fakeredis
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.services.ratelimit import LoginLimiter, RedisLoginLimiter, login_limiter
from tests.test_security import register_and_login, _login


def test_redis_login_limiter_lockout_and_retry_after():
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)
    limiter = RedisLoginLimiter(client=fake_redis)
    key = "127.0.0.1|user@example.com"

    # 4 failures should pass check
    for _ in range(4):
        limiter.check(key)
        limiter.fail(key)

    # 5th failure
    limiter.check(key)
    limiter.fail(key)

    # Now check should raise 429
    with pytest.raises(HTTPException) as exc:
        limiter.check(key)
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers
    retry_after = int(exc.value.headers["Retry-After"])
    assert 0 < retry_after <= 900  # 15 min window


def test_redis_login_limiter_isolated_keys():
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)
    limiter = RedisLoginLimiter(client=fake_redis)
    key1 = "127.0.0.1|user1@example.com"
    key2 = "127.0.0.1|user2@example.com"

    for _ in range(5):
        limiter.fail(key1)

    # key1 is locked out
    with pytest.raises(HTTPException):
        limiter.check(key1)

    # key2 should NOT be locked out
    limiter.check(key2)


def test_redis_login_limiter_reset():
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)
    limiter = RedisLoginLimiter(client=fake_redis)
    key = "127.0.0.1|user@example.com"

    for _ in range(5):
        limiter.fail(key)

    with pytest.raises(HTTPException):
        limiter.check(key)

    limiter.reset(key)
    # After reset, check should pass
    limiter.check(key)


def test_redis_login_limiter_reset_all():
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)
    limiter = RedisLoginLimiter(client=fake_redis)
    key1 = "127.0.0.1|user1@example.com"
    key2 = "127.0.0.1|user2@example.com"

    for _ in range(5):
        limiter.fail(key1)
        limiter.fail(key2)

    with pytest.raises(HTTPException):
        limiter.check(key1)
    with pytest.raises(HTTPException):
        limiter.check(key2)

    limiter.reset_all()

    limiter.check(key1)
    limiter.check(key2)


def test_redis_login_limiter_shared_across_workers():
    """Simulate two application worker processes sharing the same Redis server."""
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)
    worker_1 = RedisLoginLimiter(client=fake_redis)
    worker_2 = RedisLoginLimiter(client=fake_redis)
    key = "192.168.1.100|target@example.com"

    # Worker 1 registers 3 failed attempts
    for _ in range(3):
        worker_1.check(key)
        worker_1.fail(key)

    # Worker 2 registers 2 failed attempts
    for _ in range(2):
        worker_2.check(key)
        worker_2.fail(key)

    # Total failures is 5: both Worker 1 and Worker 2 must now lock out the user
    with pytest.raises(HTTPException) as exc1:
        worker_1.check(key)
    assert exc1.value.status_code == 429

    with pytest.raises(HTTPException) as exc2:
        worker_2.check(key)
    assert exc2.value.status_code == 429

    # Successful login/reset on Worker 1 unblocks Worker 2
    worker_1.reset(key)
    worker_2.check(key)


def test_redis_rate_limit_config_validation():
    # Invalid ratelimit backend
    with pytest.raises(ValueError, match="EVSHARE_RATELIMIT_BACKEND must be 'memory' or 'redis'"):
        Settings(ratelimit_backend="unknown")

    # Redis backend without redis_url
    with pytest.raises(ValueError, match="EVSHARE_REDIS_URL is not set"):
        Settings(ratelimit_backend="redis", redis_url="")


def test_fastapi_login_rate_limiting_with_redis(client, monkeypatch):
    """Test full login endpoint with RedisLoginLimiter backed by fakeredis."""
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)
    redis_limiter = RedisLoginLimiter(client=fake_redis)

    monkeypatch.setattr("app.services.ratelimit.settings.ratelimit_backend", "redis")
    monkeypatch.setattr(login_limiter, "_redis", redis_limiter)

    register_and_login(client)

    # 5 wrong passwords
    for _ in range(5):
        resp = _login(client, password="wrong-password")
        assert resp.status_code == 401

    # 6th attempt with correct password should be 429 locked out by Redis
    locked = _login(client)
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0

    # Reset clears lockout
    redis_limiter.reset_all()
    assert _login(client).status_code == 200

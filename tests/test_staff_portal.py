import pytest

from app.config import Settings

from .conftest import register_and_login
from .test_verification import make_admin


def _login(client, path, email, password="password123"):
    return client.post(path, data={"username": email, "password": password})


def test_staff_page_is_served_unlinked_and_noindex(client):
    r = client.get("/staff")
    assert r.status_code == 200 and "noindex" in r.headers["x-robots-tag"] and r.headers["cache-control"] == "no-store"
    assert "staff" not in client.get("/").text.lower().replace("staff-", "")  # public page never mentions it


def test_reviewers_cannot_use_the_public_login_and_users_cannot_use_staff_login(client):
    register_and_login(client, "u@example.com", "User")
    make_admin(client, "root@example.com")
    assert _login(client, "/auth/login", "root@example.com").status_code == 401        # reviewer on public entrance
    assert _login(client, "/auth/staff/login", "u@example.com").status_code == 401     # normal user on staff entrance
    assert _login(client, "/auth/login", "u@example.com").status_code == 200
    client.cookies.clear()
    ok = _login(client, "/auth/staff/login", "root@example.com")
    assert ok.status_code == 200 and "evshare_session" in ok.headers["set-cookie"]
    assert client.get("/admin/verifications").status_code == 200


def test_both_entrances_share_the_failed_login_limit(client):
    register_and_login(client, "u@example.com", "User")
    for _ in range(3):
        assert _login(client, "/auth/login", "u@example.com", "wrong-password").status_code == 401
    for _ in range(2):
        assert _login(client, "/auth/staff/login", "u@example.com", "wrong-password").status_code == 401
    assert _login(client, "/auth/login", "u@example.com").status_code == 429


@pytest.mark.parametrize("path", ["staff", "/", "/auth", "/static", "/a", "/has space", "/x/y"])
def test_staff_path_must_be_safe(path):
    with pytest.raises(ValueError):
        Settings(staff_path=path)

from .conftest import register_and_login


def _login(client, email="a@example.com", password="password123"):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_login_sets_httponly_cookie_and_cookie_auth_works(client):
    register_and_login(client)
    r = _login(client)
    cookie = r.headers["set-cookie"].lower()
    assert "evshare_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/auth/me").json()["email"] == "a@example.com"  # cookie only, no Authorization header


def test_cookie_auth_requires_csrf_header_for_writes(client):
    register_and_login(client)
    _login(client)
    body = {"title": "T", "address": "A", "latitude": 10, "longitude": 78, "connector_type": "TYPE2",
            "power_kw": 7, "price_per_kwh": 5}
    assert client.post("/chargers", json=body).status_code == 403
    assert client.post("/chargers", json=body, headers={"X-Requested-With": "evshare"}).status_code == 201


def test_bearer_clients_do_not_need_csrf_header(client):
    h = register_and_login(client)
    body = {"title": "T", "address": "A", "latitude": 10, "longitude": 78, "connector_type": "TYPE2",
            "power_kw": 7, "price_per_kwh": 5}
    assert client.post("/chargers", json=body, headers=h).status_code == 201


def test_logout_clears_session(client):
    register_and_login(client)
    _login(client)
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/logout", headers={"X-Requested-With": "evshare"}).status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_login_is_rate_limited_per_ip_and_email(client):
    register_and_login(client)
    register_and_login(client, "b@example.com", "Bala")
    for _ in range(5):
        assert _login(client, password="wrong-password").status_code == 401
    locked = _login(client)  # right password, still blocked
    assert locked.status_code == 429 and int(locked.headers["retry-after"]) > 0
    assert _login(client, "b@example.com").status_code == 200  # other accounts unaffected


def test_successful_login_resets_failure_count(client):
    register_and_login(client)
    for _ in range(4):
        _login(client, password="wrong-password")
    assert _login(client).status_code == 200
    for _ in range(4):
        assert _login(client, password="wrong-password").status_code == 401  # counter restarted


def test_security_headers_present(client):
    h = client.get("/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert "strict-origin" in h["referrer-policy"]

from .conftest import register_and_login


def _login(client, email, role=None, password="password123"):
    data = {"username": email, "password": password}
    if role is not None:
        data["expected_role"] = role
    return client.post("/auth/login", data=data)


def test_a_driver_cannot_sign_in_through_the_hub_option(client):
    register_and_login(client, "d@example.com", "Dee")
    r = _login(client, "d@example.com", "HUB")
    assert r.status_code == 403 and "driver account" in r.json()["detail"] and "Choose Driver" in r.json()["detail"]


def test_a_hub_cannot_sign_in_through_the_driver_option(client):
    register_and_login(client)  # a@example.com is a hub
    r = _login(client, "a@example.com", "DRIVER")
    assert r.status_code == 403 and "hub account" in r.json()["detail"] and "Choose Hub" in r.json()["detail"]


def test_matching_role_signs_in(client):
    register_and_login(client, "d@example.com", "Dee")
    register_and_login(client)
    assert _login(client, "d@example.com", "DRIVER").status_code == 200
    assert _login(client, "a@example.com", "HUB").status_code == 200


def test_no_role_still_signs_in_and_bad_role_is_refused(client):
    register_and_login(client, "d@example.com", "Dee")
    assert _login(client, "d@example.com").status_code == 200
    assert _login(client, "d@example.com", "ADMIN").status_code == 422


def test_wrong_password_is_still_just_incorrect(client):
    register_and_login(client, "d@example.com", "Dee")
    r = _login(client, "d@example.com", "HUB", password="wrong-password")
    assert r.status_code == 401 and r.json()["detail"] == "Incorrect email or password"

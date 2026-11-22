from fastapi.testclient import TestClient  # noqa: F401  (client fixture comes from conftest)


def test_policy_allows_the_map_tile_host_itself(client, monkeypatch):
    from app import main as main_mod
    monkeypatch.setattr(main_mod.settings, "csp_mode", "enforce")
    policy = client.get("/").headers["Content-Security-Policy"]
    img = next(d for d in policy.split("; ") if d.startswith("img-src"))
    assert "https://tile.openstreetmap.org" in img.split()
    assert "https://*.tile.openstreetmap.org" in img.split()

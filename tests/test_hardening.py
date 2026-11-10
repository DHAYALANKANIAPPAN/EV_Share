from pathlib import Path

from app import main as main_mod
from app.config import Settings

STATIC = Path(__file__).resolve().parent.parent / "static"


def test_old_interface_is_gone(client):
    assert client.get("/classic").status_code == 404
    for name in ("classic.html", "app.js", "style.css"):
        assert not (STATIC / name).exists(), name


def test_no_inline_scripts_remain_in_the_pages():
    for page in ("index.html", "staff.html"):
        html = (STATIC / page).read_text()
        assert "<script>" not in html and "onclick=" not in html, page  # every script is an external file


def test_policy_has_no_unsafe_inline_scripts_and_blocks_objects(client, monkeypatch):
    monkeypatch.setattr(main_mod.settings, "csp_mode", "enforce")
    h = client.get("/").headers
    assert "Content-Security-Policy" in h and "Content-Security-Policy-Report-Only" not in h
    policy = h["Content-Security-Policy"]
    script = next(d for d in policy.split("; ") if d.startswith("script-src"))
    assert "'unsafe-inline'" not in script and "'unsafe-eval'" not in script
    assert "object-src 'none'" in policy and "frame-ancestors 'none'" in policy and "default-src 'self'" in policy


def test_report_only_mode_reports_without_enforcing(client, monkeypatch):
    monkeypatch.setattr(main_mod.settings, "csp_mode", "report-only")
    h = client.get("/").headers
    assert "Content-Security-Policy-Report-Only" in h and "Content-Security-Policy" not in h


def test_off_sends_no_policy(client, monkeypatch):
    monkeypatch.setattr(main_mod.settings, "csp_mode", "off")
    h = client.get("/").headers
    assert "content-security-policy" not in {k.lower() for k in h.keys()}


def test_csp_mode_must_be_a_known_value():
    import pytest
    with pytest.raises(ValueError):
        Settings(csp_mode="sometimes")
    assert Settings().csp_mode == "report-only"


def test_pages_load_nothing_from_outside_the_site():
    """Everything the pages need is in the project, so the policy needs no CDN exceptions."""
    import re
    for page in ("index.html", "staff.html"):
        html = (STATIC / page).read_text()
        assert not re.search(r'(src|href)="https?://', html), page
    for name in ("css/tailwind.css", "vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "vendor/lucide.min.js",
                 "vendor/fonts/geist.css", "vendor/fonts/geist-latin-400-normal.woff2"):
        assert (STATIC / name).exists(), name


def test_policy_names_no_cdn_hosts(client, monkeypatch):
    monkeypatch.setattr(main_mod.settings, "csp_mode", "enforce")
    policy = client.get("/").headers["Content-Security-Policy"]
    for host in ("cdn.tailwindcss.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com", "fonts.googleapis.com", "fonts.gstatic.com"):
        assert host not in policy, host

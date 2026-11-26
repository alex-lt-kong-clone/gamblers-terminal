import pytest
from fastapi.testclient import TestClient

from core.registry import discover_modules


def test_landing_and_modules_open(make_app):
    c = TestClient(make_app())  # auth off
    assert c.get("/").status_code == 200
    assert c.get("/pe-monitor/").status_code == 200
    assert c.get("/ai-ratios/").status_code == 200
    assert c.get("/crypto-tracker/").status_code == 200
    assert c.get("/docs").status_code == 200


def test_prefixed_api_routes(make_app):
    c = TestClient(make_app())
    r = c.get("/pe-monitor/api/tickers")
    assert r.status_code == 200 and isinstance(r.json(), list)
    r = c.get("/ai-ratios/api/data")
    assert r.status_code == 200 and "coverage" in r.json()


def test_static_and_favicon(make_app):
    c = TestClient(make_app())
    assert c.get("/static/icon-192.png").status_code == 200
    assert c.get("/pe-monitor/static/icon.svg").status_code == 200
    assert c.get("/favicon.ico").status_code == 200


def test_openapi_tags_and_dashboards_excluded(make_app):
    oj = TestClient(make_app()).get("/openapi.json").json()
    tags = {t for p in oj["paths"].values() for op in p.values() for t in op.get("tags", [])}
    assert {"P/E Monitor", "AI Ratios", "Crypto Tracker"} <= tags
    assert "/pe-monitor/" not in oj["paths"]  # dashboard is include_in_schema=False


def test_discovery_order_and_unique_slugs():
    slugs = [m.slug for m in discover_modules()]
    assert slugs == ["pe-monitor", "averaging-calc", "ai-ratios", "crypto-tracker"]  # ordered by Module.order
    assert len(slugs) == len(set(slugs))


def test_auth_enabled_flow(make_app):
    c = TestClient(make_app(auth_tokens=["secret-abc"]))
    assert c.get("/pe-monitor/api/tickers", follow_redirects=False).status_code == 401
    c.get("/?token=secret-abc")  # sets signed cookie
    assert c.get("/pe-monitor/api/tickers").status_code == 200
    bad = TestClient(make_app(auth_tokens=["secret-abc"]))
    assert bad.get("/?token=wrong", follow_redirects=False).status_code == 401


def test_auth_revocation(make_app):
    ca = TestClient(make_app(auth_tokens=["tokA"]))
    ca.get("/?token=tokA")
    jar = ca.cookies
    cb = TestClient(make_app(auth_tokens=["tokB"]))  # same secret, tokA removed
    cb.cookies.update(jar)
    assert cb.get("/pe-monitor/api/tickers", follow_redirects=False).status_code == 401


def test_session_cookie_isolated_by_port(make_app):
    c1 = TestClient(make_app(port=9090, auth_tokens=["tok1"], secret_key="secret-one-0123456789"))
    c2 = TestClient(make_app(port=9091, auth_tokens=["tok2"], secret_key="secret-two-0123456789"))
    c1.get("/?token=tok1")
    c2.get("/?token=tok2")
    assert "gt_session_9090" in c1.cookies and "gt_session_9091" in c2.cookies
    c1.cookies.update(c2.cookies)
    assert c1.get("/pe-monitor/api/tickers").status_code == 200


def test_build_app_rejects_weak_secret_with_auth(make_app):
    with pytest.raises(RuntimeError):
        make_app(auth_tokens=["x"], secret_key="short")


def test_duplicate_slugs_rejected():
    from fastapi import APIRouter
    from core import config as hc
    from core.main import build_app
    from core.module import Module
    cfg = hc.load_config()
    dup = [
        Module(slug="dup", name="A", description="", router=APIRouter()),
        Module(slug="dup", name="B", description="", router=APIRouter()),
    ]
    with pytest.raises(RuntimeError):
        build_app(cfg, dup)

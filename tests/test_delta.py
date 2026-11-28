from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.pe_monitor import config as pcfg, storage, views
from modules.pe_monitor.views import DELTA_WINDOWS, _delta_point, _delta_rows

# Sparse live forward_pe: two real anchors with one priced gap day between them.
# EPS is constant (price/pe == 10 at both anchors), so the gap interpolates to
# price/10 — a value we can assert exactly.
ROWS = [
    {"date": "2026-01-01", "price": 100.0, "forward_pe": 10.0},  # real anchor
    {"date": "2026-01-16", "price": 150.0, "forward_pe": None},  # gap -> ~15
    {"date": "2026-02-15", "price": 200.0, "forward_pe": 20.0},  # real anchor (now)
]


@pytest.fixture
def seeded_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Daily prices with sparse forward_pe anchors and varying EPS.
    db = str(tmp_path / "pe.db")
    storage.init_db(db)
    for i in range(400):
        price = 100.0 + i % 37
        storage.append_snapshot(db, "T", {"date": (date(2025, 1, 1) + timedelta(days=i)).isoformat(), "price": price,
                                          "forward_pe": price / (8 + i % 5) if i % 9 == 0 else None})
    monkeypatch.setattr(pcfg, "load_config", lambda *a, **k: {"database_path": db, "tickers": ["T"]})
    views._cfg.cache_clear()
    yield
    views._cfg.cache_clear()


def test_delta_snaps_to_interpolated_then() -> None:
    # 30d before 2026-02-15 is 2026-01-16: the interpolated gap day, not the
    # far 2026-01-01 anchor. This is the bug interpolation prevents.
    d = _delta_point([dict(r) for r in ROWS], days=30, ytd=False)
    assert d["now_date"] == "2026-02-15" and d["now"] == 20.0
    assert d["then_date"] == "2026-01-16"
    assert d["then"] == 15.0 and d["then_interpolated"] is True
    assert d["delta"] == 5.0
    assert d["delta_pct"] == 5.0 / 15.0
    # Sparkline spans the window: first point == then, last == now.
    assert d["series"][0] == 15.0 and d["series"][-1] == 20.0
    # Decomposition: EPS is constant (10 at both ends), so the whole P/E move is
    # price; contributions sum exactly to delta_pct.
    assert d["price_change_pct"] == pytest.approx(1 / 3)
    assert d["eps_change_pct"] == 0
    assert d["price_contrib"] + d["eps_contrib"] == pytest.approx(d["delta_pct"])


def test_delta_then_none_when_window_predates_coverage() -> None:
    d = _delta_point([dict(r) for r in ROWS], days=60, ytd=False)  # target < first row
    assert d["now"] == 20.0
    assert d["then"] is None and d["delta"] is None and d["delta_pct"] is None


def test_delta_ytd_baselines_on_or_before_jan1() -> None:
    d = _delta_point([dict(r) for r in ROWS], days=None, ytd=True)
    assert d["then_date"] == "2026-01-01"  # real anchor, not interpolated
    assert d["then"] == 10.0 and d["then_interpolated"] is False
    assert d["delta_pct"] == 1.0


def test_delta_empty_series() -> None:
    d = _delta_point([], days=30, ytd=False)
    assert d["now"] is None and d["then"] is None and d["delta_pct"] is None


def test_delta_now_none_when_latest_is_a_forecast_loss() -> None:
    # Latest forward P/E is a loss (negative) -> interpolation nulls it -> `now` must be
    # N/A, not the stale pre-loss positive value.
    rows = [
        {"date": "2026-01-01", "price": 100.0, "forward_pe": 10.0},
        {"date": "2026-02-15", "price": 50.0, "forward_pe": -20.0},  # forecast loss = now
    ]
    d = _delta_point([dict(r) for r in rows], days=30, ytd=False)
    assert d["now"] is None and d["now_date"] == "2026-02-15"
    assert d["then"] is None and d["delta"] is None and d["delta_pct"] is None


def test_api_delta_shape_and_window_fallback(make_app: Callable[..., FastAPI], seeded_db: None) -> None:
    c = TestClient(make_app())
    rows = c.get("/pe-monitor/api/delta?window=3m").json()
    assert isinstance(rows, list) and rows
    keys = {"ticker", "name", "window", "now", "then", "delta", "delta_pct",
            "series", "price_change_pct", "eps_change_pct",
            "price_contrib", "eps_contrib"}
    assert keys <= rows[0].keys()
    assert all(r["window"] == "3m" for r in rows)
    # Unknown window falls back to the 1m default.
    bogus = c.get("/pe-monitor/api/delta?window=bogus").json()
    assert all(r["window"] == "1m" for r in bogus)
    assert "ytd" not in DELTA_WINDOWS  # ytd is special-cased, not a day count


def test_delta_page_renders(make_app: Callable[..., FastAPI]) -> None:
    assert TestClient(make_app()).get("/pe-monitor/delta").status_code == 200


def test_decomposition_sums_to_delta_pct(seeded_db: None) -> None:
    # The price + EPS contributions must reconstruct delta_pct.
    cfg = pcfg.load_config()
    db = cfg["database_path"]
    for t in cfg["tickers"][:6]:
        d = _delta_point(_delta_rows(db, t, 31, False), 31, False)
        assert d["price_contrib"] is not None
        assert d["price_contrib"] + d["eps_contrib"] == pytest.approx(d["delta_pct"])


def test_bounded_read_matches_full_history(seeded_db: None) -> None:
    # The bounded per-ticker read must yield exactly what interpolating the whole
    # history would — the optimization must not change any delta value.
    cfg = pcfg.load_config()
    db = cfg["database_path"]
    for t in cfg["tickers"][:6]:
        for days, ytd in [(1, False), (31, False), (366, False), (None, True)]:
            full = _delta_point(storage.read_history(db, t), days, ytd)
            bounded = _delta_point(_delta_rows(db, t, days, ytd), days, ytd)
            assert full == bounded, (t, days, ytd)

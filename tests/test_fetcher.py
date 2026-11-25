import json
import os
import tempfile
from types import SimpleNamespace

import pandas as pd

from modules.pe_monitor import fetcher, storage, views


def _mock_ticker(monkeypatch, info, earnings_estimate=None, earnings_dates=None):
    fake = SimpleNamespace(
        info=info,
        earnings_estimate=earnings_estimate,
        get_earnings_dates=lambda limit=8: earnings_dates,
    )
    monkeypatch.setattr(fetcher.yf, "Ticker", lambda _t: fake)


def test_analyst_count_from_earnings_estimate(monkeypatch):
    ee = pd.DataFrame(
        {"avg": [-4.75, -3.64], "numberOfAnalysts": [24, 25]},
        index=["0y", "+1y"],
    )
    _mock_ticker(
        monkeypatch,
        {
            "currentPrice": 38.92,
            "trailingEps": -4.74,
            "forwardEps": -1.78,
            "forwardPE": -21.86,
            "numberOfAnalystOpinions": 38,
            "currency": "USD",
            "financialCurrency": "USD",
        },
        earnings_estimate=ee,
    )
    snap = fetcher.YfinanceFetcher().fetch_pe("CRWV")
    assert snap["analyst_count"] == 25
    assert snap["forward_eps"] == -1.78
    assert snap["forward_eps_native"] is None


def test_cross_currency_reads_native_eps_and_analysts(monkeypatch):
    ee = pd.DataFrame({"avg": [28.75], "numberOfAnalysts": [36]}, index=["+1y"])
    _mock_ticker(
        monkeypatch,
        {
            "currentPrice": 337.4,
            "forwardEps": 33.62,
            "forwardPE": 10.04,
            "numberOfAnalystOpinions": 41,
            "currency": "HKD",
            "financialCurrency": "CNY",
        },
        earnings_estimate=ee,
    )
    snap = fetcher.YfinanceFetcher().fetch_pe("0700.HK")
    assert snap["analyst_count"] == 36
    assert snap["forward_eps_native"] == 28.75


def test_missing_earnings_estimate_gives_none(monkeypatch):
    _mock_ticker(
        monkeypatch,
        {"currentPrice": 2.96, "numberOfAnalystOpinions": 9, "currency": "CNY", "financialCurrency": "CNY"},
        earnings_estimate=pd.DataFrame(),
    )
    snap = fetcher.YfinanceFetcher().fetch_pe("600478.SS")
    assert snap["analyst_count"] is None
    assert snap["forward_eps_native"] is None


def test_provenance_records_live_ops_and_krx_fallbacks(monkeypatch):
    ee = pd.DataFrame({"avg": [535980.25], "numberOfAnalysts": [36]}, index=["+1y"])
    ed = pd.DataFrame({"Reported EPS": [10000.0, 20000.0, 30000.0, 40000.0]})
    _mock_ticker(
        monkeypatch,
        {"currentPrice": 1030000.0, "forwardPE": 1.9217126, "currency": "KRW", "financialCurrency": "KRW"},
        earnings_estimate=ee,
        earnings_dates=ed,
    )
    snap = fetcher.get_fetcher("000660.KS").fetch_pe("000660.KS")
    prov = json.loads(snap["provenance"])
    assert prov["price"] == "info['currentPrice']"
    assert prov["forward_pe"] == "info['forwardPE']"
    assert 'snap["price"] / fp' in prov["forward_eps"]
    assert 'ed["Reported EPS"]' in prov["trailing_eps"]
    assert 'ee.loc["+1y", "numberOfAnalysts"]' in prov["analyst_count"]


def test_provenance_persists_and_chains_hidden_negative_pe(monkeypatch):
    ee = pd.DataFrame({"avg": [-3.64], "numberOfAnalysts": [25]}, index=["+1y"])
    _mock_ticker(
        monkeypatch,
        {"currentPrice": 38.92, "forwardEps": -1.78, "forwardPE": -21.86, "currency": "USD", "financialCurrency": "USD"},
        earnings_estimate=ee,
    )
    snap = fetcher.YfinanceFetcher().fetch_pe("CRWV")
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        storage.init_db(db)
        storage.append_snapshot(db, "CRWV", snap)
        row = views._hide_nonpositive_pe(storage.latest_per_ticker(db, ["CRWV"])[0])
        assert row["forward_pe"] is None
        assert row["provenance"]["forward_eps"] == "info['forwardEps']"
        assert "info['forwardPE'] -> views.py:" in row["provenance"]["forward_pe"]
        assert "row[c] <= 0" in row["provenance"]["forward_pe"]
    finally:
        os.unlink(db)

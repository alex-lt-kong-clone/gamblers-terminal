from types import SimpleNamespace

import pandas as pd

from modules.pe_monitor import fetcher


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

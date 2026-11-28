from types import SimpleNamespace

import pandas as pd
import pytest

from modules.pe_monitor import fetcher

EE_USD = pd.DataFrame({"avg": [-4.75, -3.64], "numberOfAnalysts": [24, 25]}, index=["0y", "+1y"])
EE_CNY = pd.DataFrame({"avg": [28.75], "numberOfAnalysts": [36]}, index=["+1y"])


@pytest.mark.parametrize("ccy, fin, ee, count, native", [
    ("USD", "USD", EE_USD, 25, None),
    ("HKD", "CNY", EE_CNY, 36, 28.75),
    ("CNY", "CNY", pd.DataFrame(), None, None),
], ids=["same-ccy", "cross-ccy", "no-estimate"])
def test_earnings_estimate_fields(monkeypatch: pytest.MonkeyPatch, ccy: str, fin: str, ee: pd.DataFrame, count: int | None, native: float | None) -> None:
    info = {"currentPrice": 10.0, "numberOfAnalystOpinions": 9, "currency": ccy, "financialCurrency": fin}
    monkeypatch.setattr("modules.pe_monitor.fetcher.yf.Ticker", lambda _t: SimpleNamespace(info=info, earnings_estimate=ee))
    snap = fetcher.YfinanceFetcher().fetch_pe("T")
    assert (snap["analyst_count"], snap["forward_eps_native"]) == (count, native)

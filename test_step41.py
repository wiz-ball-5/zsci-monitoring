import numpy as np
import pandas as pd

from dashboard import (
    add_daily_components,
    components_figure,
    recent_monthly_figure,
    right_now_figure,
)


def synthetic_daily():
    dates = pd.date_range("2026-08-01", "2026-09-09", freq="D")
    n = len(dates)
    west_ssta = np.linspace(0.5, 0.7, n)
    east_ssta = np.linspace(2.5, 3.7, n)
    return pd.DataFrame({
        "date": dates,
        "west_sst": 29 + west_ssta,
        "east_sst": 25 + east_ssta,
        "west_clim_sst": 29.0,
        "east_clim_sst": 25.0,
        "zsci_daily_monitor": east_ssta - west_ssta,
    })


def synthetic_monthly():
    rows = []
    for y in [1997, 2015, 2025, 2026]:
        for m in range(1, 13):
            if y == 2026 and m > 8:
                continue
            z = 0.15 * m + (2.0 if y == 1997 else 1.6 if y == 2015 else 0)
            rows.append({
                "time": pd.Timestamp(y, m, 1),
                "year": y, "month": m,
                "zsci_monthly": z,
                "east_ssta": z + 0.5,
                "west_ssta": 0.5,
            })
    return pd.DataFrame(rows)


def test_daily_component_closure():
    d = add_daily_components(synthetic_daily())
    np.testing.assert_allclose(
        d["east_ssta"] - d["west_ssta"],
        d["zsci_daily_monitor"],
    )


def test_right_now_figure():
    d = add_daily_components(synthetic_daily())
    current = {
        "current_month": "2026-09",
        "current_mtd_zsci": 3.0,
    }
    fig = right_now_figure(
        synthetic_monthly(), d, current, [2026, 1997, 2015], "zsci"
    )
    assert len(fig.data) >= 3


def test_components_figure():
    d = add_daily_components(synthetic_daily())
    fig = components_figure(d)
    assert len(fig.data) == 3


def test_recent_monthly_figure():
    monthly = synthetic_monthly()
    had = pd.DataFrame({
        "time": pd.date_range("2025-01-01", "2026-08-01", freq="MS"),
        "zsci": np.linspace(-0.5, 2.0, 20),
        "zsci_smoothed": np.linspace(-0.4, 1.5, 20),
    })
    current = {"current_month": "2026-09", "current_mtd_zsci": 3.0}
    fig = recent_monthly_figure(had, monthly, current)
    assert len(fig.data) == 4

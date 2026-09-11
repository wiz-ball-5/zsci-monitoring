import numpy as np, pandas as pd
from dashboard import historical_figure, current_figure, hadisst_status

def test_figures():
    t = pd.date_range("2000-01-01", periods=24, freq="MS")
    had = pd.DataFrame({"time":t,"zsci":np.linspace(-1,1,24),
                        "zsci_smoothed":np.r_[np.nan,np.nan,np.linspace(-.8,.8,20),np.nan,np.nan]})
    assert len(historical_figure(had).data) >= 1
    d = pd.DataFrame({"date":pd.date_range("2026-09-01",periods=8,freq="D"),
                      "zsci_daily_monitor":np.linspace(-1.1,-.8,8)})
    m = pd.DataFrame({"month":[pd.Timestamp("2026-09-01")],
                      "latest_day":[pd.Timestamp("2026-09-08")],
                      "zsci_monthly_or_mtd":[-.92]})
    assert len(current_figure(d,m).data) >= 2
    assert hadisst_status(had)["smooth_month"] == pd.Timestamp("2001-10-01")

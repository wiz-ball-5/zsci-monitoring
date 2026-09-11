from __future__ import annotations

import calendar
from pathlib import Path

import numpy as np
import pandas as pd

from dashboard import add_daily_components, load_data


had, daily, daily_monthly, current, monthly = load_data()

print("=" * 76)
print("STEP 4.1 DATA / SCIENCE VALIDATION")
print("=" * 76)

# 1) Component closure in Step 3 daily data.
err = float(
    np.nanmax(
        np.abs(daily["zsci_daily_monitor"] - daily["zsci_from_components"])
    )
)
print(f"Daily component closure max error: {err:.3e} °C")
if err > 1e-10:
    raise SystemExit("FAIL: Daily ZSCI != East SSTA - West SSTA")

# 2) OISST monthly baseline closes to zero.
base = monthly[
    (monthly["time"] >= "1981-01-01")
    & (monthly["time"] <= "2010-12-31")
]
base_err = float(base.groupby("month")["zsci_monthly"].mean().abs().max())
print(f"Monthly 1981-2010 baseline max residual: {base_err:.3e} °C")
if base_err > 1e-10:
    raise SystemExit("FAIL: OISST monthly baseline does not close to zero")

# 3) Compare completed recent months from daily pipeline vs official monthly OISST.
d = daily.copy()
d["period"] = d["date"].dt.to_period("M")
recent_daily = []
for period, g in d.groupby("period"):
    days_in_month = calendar.monthrange(period.year, period.month)[1]
    if g["date"].dt.day.nunique() == days_in_month:
        recent_daily.append({
            "period": period,
            "daily_mean_zsci": g["zsci_daily_monitor"].mean(),
        })

if recent_daily:
    rd = pd.DataFrame(recent_daily)
    mh = monthly.copy()
    mh["period"] = mh["time"].dt.to_period("M")
    cmp = rd.merge(
        mh[["period", "zsci_monthly"]],
        on="period",
        how="inner",
    )
    if not cmp.empty:
        cmp["abs_diff"] = (
            cmp["daily_mean_zsci"] - cmp["zsci_monthly"]
        ).abs()
        print("\nCompleted-month daily-vs-monthly OISST check:")
        print(cmp.tail(6).to_string(index=False))
        max_diff = float(cmp["abs_diff"].max())
        print(f"Max recent closure difference: {max_diff:.3f} °C")
        if max_diff > 0.50:
            raise SystemExit(
                "FAIL: daily and monthly OISST ZSCI disagree by >0.50 °C"
            )
        elif max_diff > 0.15:
            print("WARNING: difference >0.15 °C; inspect preliminary/final status.")
    else:
        print("No overlap between complete daily months and monthly archive yet.")
else:
    print("No complete month in the local daily cache; monthly closure check skipped.")

# 4) Current components.
period = pd.Period(current["current_month"], freq="M")
cur = daily[daily["date"].dt.to_period("M") == period]
print("\nCurrent-month components:")
print(f"East SSTA mean: {cur['east_ssta'].mean():+.3f} °C")
print(f"West SSTA mean: {cur['west_ssta'].mean():+.3f} °C")
print(f"ZSCI mean:      {cur['zsci_daily_monitor'].mean():+.3f} °C")
print(f"JSON MTD ZSCI:  {float(current['current_mtd_zsci']):+.3f} °C")

# 5) Required comparison years.
years = set(monthly["year"].astype(int))
for y in [1997, 2015]:
    if y not in years:
        raise SystemExit(f"FAIL: required comparison year {y} missing")

print("\nRight-now comparison years 1997 and 2015 are available.")
print(f"Monthly OISST history: {monthly['time'].min():%Y-%m} -> {monthly['time'].max():%Y-%m}")
print("RESULT: PASS")

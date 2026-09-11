"""Simple Step 3 diagnostic plot for the current OISST monitoring product."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def plot_current_oisst(
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
    output_path: str | Path = "output/OISST_ZSCI_current.png",
    days_to_show: int = 120,
) -> None:
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").tail(days_to_show)
    d["rolling_7d"] = d["zsci_daily_monitor"].rolling(
        7, min_periods=1
    ).mean()

    m = monthly.copy()
    m["month"] = pd.to_datetime(m["month"])
    latest = m.sort_values("month").iloc[-1]

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 4.8))

    ax.plot(
        d["date"],
        d["zsci_daily_monitor"],
        linewidth=1.0,
        alpha=0.45,
        label="Daily ZSCI monitor",
    )
    ax.plot(
        d["date"],
        d["rolling_7d"],
        linewidth=2.0,
        label="7-day mean",
    )

    # Show current MTD only across the current calendar month.
    current_month = latest["month"]
    current = d[d["date"].dt.to_period("M") == current_month.to_period("M")]
    if not current.empty:
        ax.hlines(
            latest["zsci_monthly_or_mtd"],
            xmin=current["date"].min(),
            xmax=current["date"].max(),
            linestyles="--",
            linewidth=2.0,
            label=(
                f"Current MTD ZSCI = "
                f"{latest['zsci_monthly_or_mtd']:+.2f} °C"
            ),
        )

    ax.axhline(0, linewidth=0.8, linestyle="--")
    ax.set_title("Near-real-time ZSCI monitoring from NOAA OISST v2.1")
    ax.set_xlabel("Date")
    ax.set_ylabel("ZSCI monitoring anomaly (°C)")
    ax.grid(True, linewidth=0.4, alpha=0.35)
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)

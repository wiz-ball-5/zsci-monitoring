from __future__ import annotations

from pathlib import Path
import json
import calendar

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "processed"

PATHS = {
    "hadisst": DATA / "hadisst_zsci_current_full.csv",
    "daily": DATA / "oisst_zsci_daily.csv",
    "daily_monthly": DATA / "oisst_zsci_monthly_monitor.csv",
    "current": DATA / "current_zsci.json",
    "oisst_monthly_history": DATA / "oisst_zsci_monthly_history.csv",
}

# NCC windows used in the manuscript Figure 1. These are intentionally kept
# only as subtle historical context in the dashboard.
NCC_WARM = [
    ("1951-08","1952-01"),("1957-04","1958-07"),("1963-07","1964-01"),
    ("1965-05","1966-05"),("1968-10","1970-02"),("1972-05","1973-03"),
    ("1976-09","1977-02"),("1977-09","1978-02"),("1979-09","1980-01"),
    ("1982-04","1983-06"),("1986-08","1988-02"),("1991-05","1992-06"),
    ("1994-09","1995-03"),("1997-04","1998-04"),("2002-05","2003-03"),
    ("2004-07","2005-01"),("2006-08","2007-01"),("2009-06","2010-04"),
    ("2014-10","2016-04"),("2018-09","2019-06"),("2019-11","2020-03"),
]
NCC_COLD = [
    ("1950-01","1951-02"),("1954-07","1956-04"),("1964-05","1965-01"),
    ("1970-07","1972-01"),("1973-06","1974-06"),("1975-04","1976-04"),
    ("1984-10","1985-06"),("1988-05","1989-05"),("1995-09","1996-03"),
    ("1998-07","2000-06"),("2000-10","2001-02"),("2007-08","2008-05"),
    ("2010-06","2011-05"),("2011-08","2012-03"),("2017-10","2018-03"),
    ("2020-08","2021-03"),("2021-09","2023-01"),
]


def load_data():
    missing = [str(p) for p in PATHS.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Step 4.1 dashboard data are incomplete:\n"
            + "\n".join(missing)
            + "\n\nRun the Step 3 import and build_oisst_monthly_history.py first."
        )

    had = pd.read_csv(PATHS["hadisst"], parse_dates=["time"]).sort_values("time")
    daily = pd.read_csv(PATHS["daily"], parse_dates=["date"]).sort_values("date")
    daily_monthly = pd.read_csv(
        PATHS["daily_monthly"],
        parse_dates=["month", "latest_day"],
    ).sort_values("month")
    current = json.loads(PATHS["current"].read_text(encoding="utf-8"))
    monthly = pd.read_csv(
        PATHS["oisst_monthly_history"],
        parse_dates=["time"],
    ).sort_values("time")

    daily = add_daily_components(daily)
    return had, daily, daily_monthly, current, monthly


def add_daily_components(daily):
    d = daily.copy()
    required = {
        "east_sst", "west_sst", "east_clim_sst", "west_clim_sst",
        "zsci_daily_monitor",
    }
    missing = required.difference(d.columns)
    if missing:
        raise ValueError(
            f"Your Step 3 daily CSV is too old; missing columns: {sorted(missing)}. "
            "Re-run the corrected Step 3.3 pipeline first."
        )

    d["east_ssta"] = d["east_sst"] - d["east_clim_sst"]
    d["west_ssta"] = d["west_sst"] - d["west_clim_sst"]
    d["zsci_from_components"] = d["east_ssta"] - d["west_ssta"]
    return d


def hadisst_status(had):
    raw = had.dropna(subset=["zsci"]).sort_values("time")
    sm = had.dropna(subset=["zsci_smoothed"]).sort_values("time")
    return {
        "raw_month": raw.iloc[-1]["time"],
        "raw_value": float(raw.iloc[-1]["zsci"]),
        "smooth_month": sm.iloc[-1]["time"],
        "smooth_value": float(sm.iloc[-1]["zsci_smoothed"]),
    }


def current_component_status(daily, current):
    current_month = pd.Period(current["current_month"], freq="M")
    d = daily[daily["date"].dt.to_period("M") == current_month]
    if d.empty:
        d = daily.tail(1)
    return {
        "east_ssta": float(d["east_ssta"].mean()),
        "west_ssta": float(d["west_ssta"].mean()),
        "zsci": float(d["zsci_daily_monitor"].mean()),
    }


def _base_layout(fig, title, ytitle, height=470):
    fig.update_layout(
        template="plotly_white",
        title=title,
        xaxis_title=None,
        yaxis_title=ytitle,
        hovermode="x unified",
        height=height,
        margin={"l": 60, "r": 30, "t": 75, "b": 55},
        legend={"orientation": "h", "y": 1.03, "x": 0},
        font={"family": "Inter, system-ui, sans-serif"},
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


def current_figure(daily, daily_monthly, days=120):
    d = daily.tail(days).copy()
    d["mean7"] = d["zsci_daily_monitor"].rolling(7, min_periods=1).mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["zsci_daily_monitor"], mode="lines",
        name="Daily ZSCI", opacity=0.32, line={"width": 1.2},
        hovertemplate="%{x|%Y-%m-%d}<br>Daily %{y:+.2f} °C<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["mean7"], mode="lines",
        name="7-day mean", line={"width": 3},
        hovertemplate="%{x|%Y-%m-%d}<br>7-day %{y:+.2f} °C<extra></extra>",
    ))

    latest = daily_monthly.iloc[-1]
    month = pd.Timestamp(latest["month"])
    cur = d[d["date"].dt.to_period("M") == month.to_period("M")]
    if not cur.empty:
        y = float(latest["zsci_monthly_or_mtd"])
        fig.add_trace(go.Scatter(
            x=[cur["date"].min(), cur["date"].max()],
            y=[y, y], mode="lines",
            name=f"Current MTD {y:+.2f} °C",
            line={"dash": "dash", "width": 2.5},
            hovertemplate=f"Current MTD {y:+.2f} °C<extra></extra>",
        ))

    fig.add_hline(y=0, line_dash="dash", line_width=1, opacity=0.6)
    return _base_layout(
        fig,
        "Near-real-time ZSCI · NOAA OISST v2.1",
        "ZSCI anomaly (°C)",
        455,
    )


def components_figure(daily, days=120):
    d = daily.tail(days).copy()
    for col in ["east_ssta", "west_ssta", "zsci_daily_monitor"]:
        d[col + "_7d"] = d[col].rolling(7, min_periods=1).mean()

    fig = go.Figure()
    for col, label in [
        ("east_ssta_7d", "East SSTA · 7-day mean"),
        ("west_ssta_7d", "West SSTA · 7-day mean"),
        ("zsci_daily_monitor_7d", "ZSCI = East − West"),
    ]:
        fig.add_trace(go.Scatter(
            x=d["date"], y=d[col], mode="lines",
            name=label,
            line={"width": 3 if col.startswith("zsci") else 2},
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:+.2f} °C<extra></extra>",
        ))

    fig.add_hline(y=0, line_dash="dash", line_width=1, opacity=0.6)
    return _base_layout(
        fig,
        "What is driving ZSCI?",
        "SST anomaly (°C)",
        440,
    )


def right_now_figure(monthly, daily, current, selected_years=None, metric="zsci"):
    metric_map = {
        "zsci": ("zsci_monthly", "ZSCI anomaly (°C)", "ZSCI"),
        "east": ("east_ssta", "East SSTA (°C)", "East SSTA"),
        "west": ("west_ssta", "West SSTA (°C)", "West SSTA"),
    }
    col, ytitle, label = metric_map.get(metric, metric_map["zsci"])

    current_year = int(pd.Period(current["current_month"], freq="M").year)
    if selected_years is None:
        selected_years = [current_year, 1997, 2015]
    selected_years = [int(y) for y in selected_years]

    hist = monthly[monthly["year"] >= 1982].copy()
    fig = go.Figure()

    # Every unselected year = quiet gray context.
    for year, g in hist.groupby("year"):
        if int(year) in selected_years:
            continue
        fig.add_trace(go.Scatter(
            x=g["month"], y=g[col],
            mode="lines",
            line={"color": "rgba(80, 93, 108, 0.18)", "width": 1},
            hoverinfo="skip",
            showlegend=False,
        ))

    # Current MTD component values.
    current_period = pd.Period(current["current_month"], freq="M")
    current_daily = daily[
        daily["date"].dt.to_period("M") == current_period
    ]
    current_mtd = {
        "zsci": float(current["current_mtd_zsci"]),
        "east": float(current_daily["east_ssta"].mean()),
        "west": float(current_daily["west_ssta"].mean()),
    }[metric]

    palette = qualitative.Safe
    selected_order = [current_year] + [
        y for y in selected_years if y != current_year
    ]

    for i, year in enumerate(selected_order):
        if year not in selected_years:
            continue
        g = hist[hist["year"] == year][["month", col]].copy()

        if year == current_year:
            # Replace/append the current month with Step-3 MTD.
            g = g[g["month"] != current_period.month]
            g = pd.concat([
                g,
                pd.DataFrame({
                    "month": [current_period.month],
                    col: [current_mtd],
                }),
            ], ignore_index=True).sort_values("month")

        if g.empty:
            continue

        color = "#f05a28" if year == current_year else palette[(i + 1) % len(palette)]
        width = 4 if year == current_year else 3
        text = [""] * len(g)
        text[-1] = f"{year} {float(g.iloc[-1][col]):+.2f}°C"

        fig.add_trace(go.Scatter(
            x=g["month"], y=g[col],
            mode="lines+markers+text",
            text=text,
            textposition="top right",
            cliponaxis=False,
            name=str(year),
            line={"color": color, "width": width},
            marker={"size": 7 if year == current_year else 5},
            hovertemplate=(
                f"{year} · %{{x}}<br>{label}: %{{y:+.2f}} °C<extra></extra>"
            ),
        ))

    fig.add_hline(y=0, line_dash="dash", line_width=1, opacity=0.55)
    fig.update_xaxes(
        range=[0.65, 12.35],
        tickmode="array",
        tickvals=list(range(1, 13)),
        ticktext=[
            "Jan","Feb","Mar","Apr","May","Jun",
            "Jul","Aug","Sep","Oct","Nov","Dec",
        ],
        fixedrange=False,
    )

    _base_layout(
        fig,
        f"This year vs every year since 1982 · {label}",
        ytitle,
        520,
    )
    fig.update_layout(hovermode="closest")
    return fig


def recent_monthly_figure(had, monthly, current, months=24):
    latest_month = pd.Period(current["current_month"], freq="M").to_timestamp()
    start = latest_month - pd.DateOffset(months=months - 1)

    h = had[had["time"] >= start].copy()
    o = monthly[monthly["time"] >= start].copy()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=o["time"], y=o["zsci_monthly"],
        mode="lines+markers",
        name="OISST monthly ZSCI · unsmoothed",
        line={"width": 2.7},
        marker={"size": 6},
        hovertemplate="%{x|%Y-%m}<br>OISST monthly %{y:+.2f} °C<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=h["time"], y=h["zsci"],
        mode="lines+markers",
        name="HadISST monthly ZSCI · unsmoothed",
        line={"width": 1.6, "dash": "dot"},
        marker={"size": 4},
        hovertemplate="%{x|%Y-%m}<br>HadISST raw %{y:+.2f} °C<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=h["time"], y=h["zsci_smoothed"],
        mode="lines",
        name="HadISST finalized · 5-month smoothed",
        line={"width": 2.2, "dash": "dash"},
        hovertemplate="%{x|%Y-%m}<br>HadISST 5m %{y:+.2f} °C<extra></extra>",
    ))

    current_x = latest_month
    current_y = float(current["current_mtd_zsci"])
    fig.add_trace(go.Scatter(
        x=[current_x], y=[current_y],
        mode="markers+text",
        text=[f"MTD {current_y:+.2f}°C"],
        textposition="top center",
        name="Current OISST MTD",
        marker={"size": 14, "symbol": "star"},
        hovertemplate=(
            f"{current['current_month']} MTD<br>"
            f"{current_y:+.2f} °C<extra></extra>"
        ),
    ))

    fig.add_hline(y=0, line_dash="dash", line_width=1, opacity=0.55)
    return _base_layout(
        fig,
        "Recent monthly context · raw vs smoothed",
        "ZSCI anomaly (°C)",
        460,
    )


def historical_figure(had):
    fig = go.Figure()
    final = had.dropna(subset=["zsci_smoothed"]).copy()
    raw = had.dropna(subset=["zsci"]).copy()

    # Subtle manuscript-event windows.
    for start, end in NCC_WARM:
        fig.add_vrect(
            x0=pd.Timestamp(start), x1=pd.Timestamp(end),
            fillcolor="rgba(220, 70, 70, 0.08)",
            line_width=0, layer="below",
        )
    for start, end in NCC_COLD:
        fig.add_vrect(
            x0=pd.Timestamp(start), x1=pd.Timestamp(end),
            fillcolor="rgba(60, 120, 210, 0.08)",
            line_width=0, layer="below",
        )

    fig.add_trace(go.Scatter(
        x=final["time"], y=final["zsci_smoothed"],
        mode="lines",
        name="HadISST ZSCI · 5-month smoothed",
        line={"width": 2.2},
        hovertemplate="%{x|%Y-%m}<br>ZSCI %{y:+.2f} °C<extra></extra>",
    ))

    tail = raw[raw["time"] >= raw["time"].max() - pd.DateOffset(months=18)]
    fig.add_trace(go.Scatter(
        x=tail["time"], y=tail["zsci"],
        mode="lines+markers",
        name="Recent raw monthly ZSCI",
        line={"dash": "dot", "width": 1.6},
        marker={"size": 5},
        hovertemplate="%{x|%Y-%m}<br>Raw %{y:+.2f} °C<extra></extra>",
    ))

    # Legend keys for event shading.
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        marker={"size": 12, "symbol": "square", "color": "rgba(220,70,70,0.18)"},
        name="NCC El Niño window",
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        marker={"size": 12, "symbol": "square", "color": "rgba(60,120,210,0.18)"},
        name="NCC La Niña window",
    ))

    fig.add_hline(y=0, line_dash="dash", line_width=1, opacity=0.55)

    _base_layout(fig, "Historical ZSCI", "ZSCI anomaly (°C)", 500)

    xmin = raw["time"].min()
    xmax = raw["time"].max()
    # Public default: 1950-present to match the manuscript analysis period.
    # The "All" button still exposes the full HadISST record.
    default_xmin = max(xmin, pd.Timestamp("1950-01-01"))
    fig.update_xaxes(
        range=[default_xmin, xmax],
        rangeslider={"visible": True, "thickness": 0.08},
        rangeselector={"buttons": [
            {"count": 10, "label": "10y", "step": "year", "stepmode": "backward"},
            {"count": 25, "label": "25y", "step": "year", "stepmode": "backward"},
            {"label": "All", "step": "all"},
        ]},
    )
    return fig

from __future__ import annotations

import os

from dash import Dash, Input, Output, dcc, html

from dashboard import (
    components_figure,
    current_component_status,
    current_figure,
    hadisst_status,
    historical_figure,
    load_data,
    recent_monthly_figure,
    right_now_figure,
)


had, daily, daily_monthly, current, monthly = load_data()
hs = hadisst_status(had)
components = current_component_status(daily, current)

CURRENT_YEAR = int(current["current_month"][:4])
AVAILABLE_YEARS = sorted(
    set(monthly.loc[monthly["year"] >= 1982, "year"].astype(int))
    | {CURRENT_YEAR}
)

DEFAULT_YEARS = [
    y for y in [CURRENT_YEAR, 1997, 2015]
    if y in AVAILABLE_YEARS
]

app = Dash(__name__)
app.title = "ZSCI Monitoring"
server = app.server


def signed(v):
    return f"{float(v):+.2f} °C"


def card(label, value, foot, primary=False):
    return html.Div(
        className="metric-card" + (" primary" if primary else ""),
        children=[
            html.Div(label, className="metric-label"),
            html.Div(value, className="metric-value"),
            html.Div(foot, className="metric-foot"),
        ],
    )


status = str(current.get("latest_daily_oisst_status", "unknown")).lower()

app.layout = html.Div([
    html.Header(className="hero", children=[
        html.Div(className="hero-inner", children=[
            html.Div([
                html.Div("ZSCI MONITORING", className="eyebrow"),
                html.H1("Zonal SST Contrast Index"),
                html.P(
                    "A basin-scale ENSO diagnostic based on the anomalous east–west "
                    "sea-surface-temperature contrast across the equatorial Pacific."
                ),
            ]),
            html.Div(className="definition", children=[
                html.B("ZSCI v1.0"),
                html.Div("East SSTA − West SSTA", className="definition-main"),
                html.Small(
                    "5°S–5°N · East 155°W–70°W · West 120°E–155°W · "
                    "1981–2010 baseline"
                ),
            ]),
        ]),
    ]),

    html.Main(className="main", children=[
        html.Section(className="section", children=[
            html.Div(className="section-head", children=[
                html.Div([
                    html.H2("Current conditions"),
                    html.P(
                        "Near-real-time NOAA OISST v2.1 monitoring. "
                        "Current daily/MTD values are provisional."
                    ),
                ]),
                html.Span(status.upper(), className="status " + status),
            ]),
            html.Div(className="metrics", children=[
                card(
                    "Current MTD ZSCI",
                    signed(current["current_mtd_zsci"]),
                    f'{current["current_month"]} · '
                    f'{current["mtd_days_available"]}/{current["mtd_days_in_month"]} days',
                    True,
                ),
                card(
                    "Latest daily ZSCI",
                    signed(current["latest_daily_zsci"]),
                    current["latest_observation_date"],
                ),
                card(
                    "Latest finalized HadISST",
                    signed(hs["smooth_value"]),
                    f'{hs["smooth_month"]:%Y-%m} · 5-month smoothed',
                ),
                card(
                    "OISST MTD coverage",
                    f'{100*float(current["mtd_coverage_fraction"]):.0f}%',
                    "Available days this month",
                ),
            ]),
        ]),

        html.Section(className="section panel", children=[
            html.Div(className="numbered-head", children=[
                html.Div("01", className="section-number"),
                html.Div([
                    html.H2("Right now"),
                    html.P(
                        "Compare the same calendar months across the OISST record. "
                        "All years are shown in gray; selected years are highlighted. "
                        "The current month uses the live MTD value."
                    ),
                ]),
            ]),
            html.Div(className="controls", children=[
                html.Div([
                    html.Label("Highlight years"),
                    dcc.Dropdown(
                        id="year-selector",
                        options=[{"label": str(y), "value": y} for y in AVAILABLE_YEARS],
                        value=DEFAULT_YEARS,
                        multi=True,
                        clearable=True,
                        className="year-dropdown",
                    ),
                ], className="control-block wide"),
                html.Div([
                    html.Label("Metric"),
                    dcc.RadioItems(
                        id="metric-selector",
                        options=[
                            {"label": "ZSCI", "value": "zsci"},
                            {"label": "East SSTA", "value": "east"},
                            {"label": "West SSTA", "value": "west"},
                        ],
                        value="zsci",
                        inline=True,
                        className="radio-row",
                    ),
                ], className="control-block"),
            ]),
            dcc.Loading(
                dcc.Graph(
                    id="right-now-chart",
                    figure=right_now_figure(
                        monthly, daily, current, DEFAULT_YEARS, "zsci"
                    ),
                    config={"displaylogo": False, "responsive": True},
                ),
                type="circle",
            ),
            html.Div(
                "Monthly view is intentional: it keeps the all-year comparison on the "
                "canonical monthly ZSCI definition. The separate panel below retains "
                "daily near-real-time monitoring.",
                className="figure-note",
            ),
        ]),

        html.Section(className="section panel", children=[
            html.Div(className="numbered-head", children=[
                html.Div("02", className="section-number"),
                html.Div([
                    html.H2("Near-real-time evolution"),
                    html.P(
                        "Daily OISST ZSCI, its 7-day mean, and the current month-to-date mean."
                    ),
                ]),
            ]),
            dcc.Graph(
                figure=current_figure(daily, daily_monthly),
                config={"displaylogo": False, "responsive": True},
            ),
        ]),

        html.Section(className="section panel", children=[
            html.Div(className="numbered-head", children=[
                html.Div("03", className="section-number"),
                html.Div([
                    html.H2("Components"),
                    html.P(
                        "ZSCI becomes large when the eastern Pacific anomaly exceeds "
                        "the western Pacific anomaly. This panel shows that decomposition directly."
                    ),
                ]),
            ]),
            html.Div(className="component-cards", children=[
                card("Current East SSTA", signed(components["east_ssta"]), "Current-month mean"),
                card("Current West SSTA", signed(components["west_ssta"]), "Current-month mean"),
                card("East − West", signed(components["zsci"]), "Equals current MTD ZSCI", True),
            ]),
            dcc.Graph(
                figure=components_figure(daily),
                config={"displaylogo": False, "responsive": True},
            ),
        ]),

        html.Section(className="section panel", children=[
            html.Div(className="numbered-head", children=[
                html.Div("04", className="section-number"),
                html.Div([
                    html.H2("Recent monthly context"),
                    html.P(
                        "Raw OISST and HadISST monthly ZSCI are shown alongside the "
                        "finalized 5-month HadISST series and the current OISST MTD point."
                    ),
                ]),
            ]),
            dcc.Graph(
                figure=recent_monthly_figure(had, monthly, current),
                config={"displaylogo": False, "responsive": True},
            ),
            html.Div(
                "Use raw monthly lines when comparing amplitudes across products. "
                "The 5-month HadISST line is intentionally smoother and should not be "
                "used as a direct peak-to-peak comparison with MTD.",
                className="figure-note important",
            ),
        ]),

        html.Section(className="section panel", children=[
            html.Div(className="numbered-head", children=[
                html.Div("05", className="section-number"),
                html.Div([
                    html.H2("Historical context"),
                    html.P(
                        "Canonical HadISST ZSCI with manuscript NCC El Niño / La Niña "
                        "windows. Use 10y, 25y, All, or the range slider."
                    ),
                ]),
            ]),
            dcc.Graph(
                figure=historical_figure(had),
                config={"displaylogo": False, "responsive": True},
            ),
        ]),

        html.Section(className="section method", children=[
            html.Div([
                html.H2("How to read the dashboard"),
                html.P(
                    "Positive ZSCI means the climatological west-warm / east-cold SST "
                    "contrast has weakened; negative ZSCI means it has strengthened."
                ),
                html.P(
                    "The current OISST MTD value is a daily-based provisional estimate. "
                    "The historical HadISST reference shown as 'finalized' is a centered "
                    "5-month-smoothed series, so its peak amplitude is not directly "
                    "comparable to a current MTD value."
                ),
            ]),
            html.Div(className="spec", children=[
                html.B("INDEX SPECIFICATION"),
                html.Div("Version"), html.Strong("ZSCI v1.0"),
                html.Div("Baseline"), html.Strong("1981–2010"),
                html.Div("Spatial weighting"), html.Strong("cos(latitude)"),
                html.Div("Historical smoothing"), html.Strong("5-month cosine-bell"),
                html.Div("Operational SST"), html.Strong("NOAA OISST v2.1"),
            ]),
        ]),
    ]),

    html.Footer([
        html.B("ZSCI Monitoring · v1.0"),
        html.Span(f'OISST through {current["latest_observation_date"]}'),
    ]),
])


@app.callback(
    Output("right-now-chart", "figure"),
    Input("year-selector", "value"),
    Input("metric-selector", "value"),
)
def update_right_now(selected_years, metric):
    selected_years = selected_years or [CURRENT_YEAR]
    if CURRENT_YEAR not in selected_years:
        selected_years = [CURRENT_YEAR] + list(selected_years)
    return right_now_figure(
        monthly,
        daily,
        current,
        selected_years=selected_years,
        metric=metric,
    )


if __name__ == "__main__":
    # Production-like local mode by default so the Dash developer toolbar
    # does not cover the scientific figures.
    debug = os.environ.get("ZSCI_DEBUG", "0") == "1"
    app.run(debug=debug, host="127.0.0.1", port=8050)

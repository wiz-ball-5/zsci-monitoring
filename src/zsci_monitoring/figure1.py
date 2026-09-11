"""Exact Figure 1 plotting logic adapted from the manuscript notebook."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from .events import NCC_COLD_DF, NCC_WARM_DF

COL_WARM = "#D62728"
COL_COLD = "#1F77B4"


def plot_figure1(
    z: xr.DataArray,
    png_path: str | Path,
    pdf_path: str | Path,
) -> None:
    png_path = Path(png_path)
    pdf_path = Path(pdf_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 4.3))
    ax.plot(
        z.time.values,
        z.values,
        color="0.05",
        lw=2.1,
        label="ZSCI (5-month smoothed)",
        zorder=2,
    )
    ax.axhline(0, color="0.35", lw=0.8, ls="--")

    for i, (_, row) in enumerate(NCC_WARM_DF.iterrows()):
        ax.axvspan(
            row.start,
            row.end,
            color=COL_WARM,
            alpha=0.12,
            lw=0,
            label="El Niño" if i == 0 else None,
        )

    for i, (_, row) in enumerate(NCC_COLD_DF.iterrows()):
        ax.axvspan(
            row.start,
            row.end,
            color=COL_COLD,
            alpha=0.12,
            lw=0,
            label="La Niña" if i == 0 else None,
        )

    ax.set_xlim(pd.Timestamp("1945-06-01"), pd.Timestamp("2025-06-01"))
    y_vals = z.values[np.isfinite(z.values)]
    y_data_max = float(np.nanmax(y_vals))
    y_data_min = float(np.nanmin(y_vals))
    ax.set_ylim(y_data_min * 1.18, y_data_max * 1.10)

    def _get_yv(peak_t):
        sub = z.sel(
            time=(
                (z.time.dt.year == peak_t.year)
                & (z.time.dt.month == peak_t.month)
            )
        )
        return float(sub.values[0]) if sub.time.size else None

    y_max_safe = y_data_max * 1.06

    def _annotate_warm(peak_t, label, dy_pts=12):
        yv = _get_yv(peak_t)
        if yv is None:
            return
        if yv > y_max_safe * 0.88:
            ax.text(
                peak_t,
                yv + 0.04,
                label,
                ha="center",
                va="bottom",
                fontsize=8.8,
                fontweight="bold",
                color=COL_WARM,
                bbox=dict(fc="white", ec="none", alpha=0.75, pad=0.2),
                zorder=5,
                clip_on=True,
            )
        else:
            ax.annotate(
                label,
                xy=(peak_t, yv),
                xytext=(0, dy_pts),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8.8,
                fontweight="bold",
                color=COL_WARM,
                bbox=dict(fc="white", ec="none", alpha=0.75, pad=0.2),
                zorder=5,
            )

    for _, row in NCC_WARM_DF.iterrows():
        peak_t = row.peak
        if pd.Timestamp("1950-01-01") <= peak_t <= pd.Timestamp("2024-12-31"):
            _annotate_warm(peak_t, row.label)

    cold_annots = []
    for _, row in NCC_COLD_DF.iterrows():
        peak_t = row.peak
        if pd.Timestamp("1950-01-01") <= peak_t <= pd.Timestamp("2024-12-31"):
            yv = _get_yv(peak_t)
            if yv is not None:
                cold_annots.append((peak_t, yv, row.label))

    cold_annots.sort(key=lambda t: t[0])
    used_x_offsets = {}

    for j, (peak_t, yv, label) in enumerate(cold_annots):
        x_off_months = 0
        if j > 0:
            prev_t = cold_annots[j - 1][0]
            gap_months = (
                (peak_t.year - prev_t.year) * 12
                + (peak_t.month - prev_t.month)
            )
            if gap_months < 18:
                used_x_offsets[prev_t] = -8
                x_off_months = 8

        if peak_t in used_x_offsets:
            x_off_months = used_x_offsets[peak_t]

        shifted_t = peak_t + pd.DateOffset(months=x_off_months)

        ax.annotate(
            label,
            xy=(peak_t, yv),
            xytext=(shifted_t, yv - 0.14),
            textcoords="data",
            ha="center",
            va="top",
            fontsize=8.8,
            fontweight="bold",
            color=COL_COLD,
            bbox=dict(fc="white", ec="none", alpha=0.75, pad=0.2),
            arrowprops=(
                dict(
                    arrowstyle="-",
                    color=COL_COLD,
                    lw=0.6,
                    alpha=0.5,
                )
                if x_off_months != 0
                else None
            ),
            zorder=5,
        )

    ax.set_title("Historical ZSCI time series with NCC El Niño / La Niña windows")
    ax.set_ylabel("SST anomaly (°C)")
    ax.set_xlabel("Year")
    ax.grid(True, color="0.88", lw=0.45)
    ax.legend(loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    plt.savefig(pdf_path, bbox_inches="tight", dpi=300)
    plt.savefig(png_path, bbox_inches="tight", dpi=300)
    plt.close(fig)

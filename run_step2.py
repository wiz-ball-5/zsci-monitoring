"""
One-command Step 2 workflow.

Usage:
    python run_step2.py
    python run_step2.py --refresh
"""

from __future__ import annotations

import argparse
from pathlib import Path
import json

import numpy as np
import pandas as pd
import xarray as xr

from zsci_monitoring.download import download_hadisst
from zsci_monitoring.figure1 import plot_figure1
from zsci_monitoring.legacy_notebook import legacy_compute_zsci
from zsci_monitoring.zsci import (
    SPEC,
    compute_zsci,
    prepare_sst_dataarray,
)


MANUSCRIPT_RANGE = ("1950-01-01", "2023-12-31")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-download the current official HadISST archive.",
    )
    args = parser.parse_args()

    raw_dir = Path("data/raw")
    processed_dir = Path("data/processed")
    metadata_dir = Path("data/metadata")
    output_dir = Path("output")
    for d in [raw_dir, processed_dir, metadata_dir, output_dir]:
        d.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("STEP 2A — Obtain official HadISST1")
    print("=" * 72)
    hadisst_path = download_hadisst(
        data_dir=raw_dir,
        metadata_dir=metadata_dir,
        refresh=args.refresh,
    )

    print()
    print("=" * 72)
    print("STEP 2B — Reproduce manuscript ZSCI (1950–2023)")
    print("=" * 72)

    ds = xr.open_dataset(hadisst_path)
    sst_all = prepare_sst_dataarray(ds)

    # Exact notebook behavior for Figure 1:
    # subset to 1950–2023 BEFORE the centered smoothing.
    sst_manuscript = sst_all.sel(time=slice(*MANUSCRIPT_RANGE))
    manuscript = compute_zsci(sst_manuscript)

    manuscript_df = manuscript[
        ["west_sst", "east_sst", "raw_contrast", "zsci", "zsci_smoothed"]
    ].to_dataframe().reset_index()
    manuscript_csv = processed_dir / "hadisst_zsci_manuscript_1950_2023.csv"
    manuscript_df.to_csv(manuscript_csv, index=False)

    z_plot = manuscript["zsci_smoothed"].dropna("time")
    png_path = output_dir / "Fig1_ZSCI_timeseries_reproduced.png"
    pdf_path = output_dir / "Fig1_ZSCI_timeseries_reproduced.pdf"
    plot_figure1(z_plot, png_path=png_path, pdf_path=pdf_path)

    print(f"Saved manuscript CSV: {manuscript_csv}")
    print(f"Saved Figure 1 PNG:    {png_path}")
    print(f"Saved Figure 1 PDF:    {pdf_path}")

    print()
    print("=" * 72)
    print("STEP 2C — Numerical refactor validation against notebook logic")
    print("=" * 72)

    legacy_raw, legacy_sm = legacy_compute_zsci(hadisst_path)

    new_raw, old_raw = xr.align(
        manuscript["zsci"].dropna("time"),
        legacy_raw.dropna("time"),
        join="inner",
    )
    new_sm, old_sm = xr.align(
        manuscript["zsci_smoothed"].dropna("time"),
        legacy_sm.dropna("time"),
        join="inner",
    )

    raw_max_abs = float(np.nanmax(np.abs(new_raw.values - old_raw.values)))
    sm_max_abs = float(np.nanmax(np.abs(new_sm.values - old_sm.values)))

    tolerance = 1e-12
    passed = raw_max_abs <= tolerance and sm_max_abs <= tolerance

    report = [
        "ZSCI Step 2 refactor validation",
        "================================",
        f"ZSCI version: {SPEC.version}",
        f"Input: {hadisst_path}",
        f"Manuscript range: {MANUSCRIPT_RANGE[0]} to {MANUSCRIPT_RANGE[1]}",
        f"Raw overlapping months: {new_raw.sizes['time']}",
        f"Smoothed overlapping months: {new_sm.sizes['time']}",
        f"Max |new raw - notebook raw|: {raw_max_abs:.16e} °C",
        f"Max |new smoothed - notebook smoothed|: {sm_max_abs:.16e} °C",
        f"Tolerance: {tolerance:.1e} °C",
        f"RESULT: {'PASS' if passed else 'FAIL'}",
    ]

    report_text = "\n".join(report)
    print(report_text)
    report_path = output_dir / "refactor_validation.txt"
    report_path.write_text(report_text + "\n", encoding="utf-8")

    if not passed:
        raise SystemExit(
            "Validation failed. Do not proceed to Step 3 until this is resolved."
        )

    print()
    print("=" * 72)
    print("STEP 2D — Build current full-record HadISST ZSCI for future dashboard")
    print("=" * 72)

    # Operational series: compute on the entire currently available archive.
    full = compute_zsci(sst_all)
    full_df = full[
        ["west_sst", "east_sst", "raw_contrast", "zsci", "zsci_smoothed"]
    ].to_dataframe().reset_index()
    full_csv = processed_dir / "hadisst_zsci_current_full.csv"
    full_df.to_csv(full_csv, index=False)

    baseline_contrast = (
        full["raw_contrast"]
        .sel(time=slice("1981-01-01", "2010-12-31"))
        .groupby("time.month")
        .mean("time")
    )
    clim_df = pd.DataFrame(
        {
            "month": np.arange(1, 13),
            "raw_contrast_climatology_degC": baseline_contrast.values,
        }
    )
    clim_csv = processed_dir / "hadisst_zsci_climatology_1981_2010.csv"
    clim_df.to_csv(clim_csv, index=False)

    latest_raw = pd.Timestamp(full["zsci"].dropna("time").time.values[-1])
    latest_sm = pd.Timestamp(full["zsci_smoothed"].dropna("time").time.values[-1])

    print(f"Saved full current series: {full_csv}")
    print(f"Saved baseline climatology: {clim_csv}")
    print(f"Latest raw monthly ZSCI: {latest_raw:%Y-%m}")
    print(f"Latest finalized 5-month smoothed ZSCI: {latest_sm:%Y-%m}")
    print()
    print("STEP 2 COMPLETE ✅")
    print("Next: Step 3 will add OISST daily and month-to-date ZSCI.")

    ds.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path

from zsci_monitoring.oisst import (
    backup_broken_v03_outputs,
    build_daily_climatology,
    build_monthly_monitor,
    update_recent_daily_zsci,
    validate_latest_scientific_sanity,
    validate_monitoring_identity,
    write_current_summary,
)
from zsci_monitoring.plot_current import plot_current_oisst


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rebuild-climatology",
        action="store_true",
        help="Rebuild the validated NOAA/PSL 1981-2010 DAILY climatology CSV.",
    )
    parser.add_argument(
        "--refresh-climatology-source",
        action="store_true",
        help="Re-download the NOAA/PSL daily climatology NetCDF.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=120,
        help="Initial monitoring context (default 120 days).",
    )
    args = parser.parse_args()

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    Path("data/raw/oisst_daily").mkdir(parents=True, exist_ok=True)
    Path("data/raw/oisst_climatology").mkdir(parents=True, exist_ok=True)
    Path("output").mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("STEP 3.2A — Detect and quarantine the old zero-climatology output")
    print("=" * 78)
    repaired = backup_broken_v03_outputs()
    print("Broken legacy output detected:", repaired)

    print()
    print("=" * 78)
    print("STEP 3.2B — Build VALIDATED OISST daily climatology (1981–2010)")
    print("=" * 78)
    climatology = build_daily_climatology(
        force=args.rebuild_climatology,
        refresh_source=args.refresh_climatology_source,
    )

    print()
    print("=" * 78)
    print("STEP 3.2C — Reprocess/download recent NOAA OISST daily data")
    print("=" * 78)
    daily = update_recent_daily_zsci(
        climatology=climatology,
        initial_lookback_days=args.lookback_days,
    )

    print()
    print("=" * 78)
    print("STEP 3.2D — Build monthly / month-to-date monitor")
    print("=" * 78)
    monthly = build_monthly_monitor(daily)

    print()
    print("=" * 78)
    print("STEP 3.2E — Numerical AND scientific sanity checks")
    print("=" * 78)
    err = validate_monitoring_identity(daily, monthly)
    validate_latest_scientific_sanity(daily)
    print(f"Max MTD identity error: {err:.16e} °C")
    print("Scientific sign/baseline sanity: PASS")
    print("RESULT: PASS")

    summary = write_current_summary(daily, monthly)
    plot_current_oisst(
        daily,
        monthly,
        output_path="output/OISST_ZSCI_current.png",
    )
    print("Saved updated plot: output/OISST_ZSCI_current.png")

    print()
    print("=" * 78)
    print("CORRECTED CURRENT ZSCI MONITORING STATUS")
    print("=" * 78)
    print(f"Latest OISST date:             {summary['latest_observation_date']}")
    print(f"Latest raw E-W contrast:       {summary['latest_raw_contrast']:+.3f} °C")
    print(
        f"Daily climatological E-W:      "
        f"{summary['latest_climatological_contrast']:+.3f} °C"
    )
    print(f"Latest daily ZSCI:             {summary['latest_daily_zsci']:+.3f} °C")
    print(
        f"NOAA native anom E-W (71-00): "
        f"{summary['latest_native_anom_contrast_1971_2000']:+.3f} °C"
    )
    print(f"Current month:                 {summary['current_month']}")
    print(f"Current MTD ZSCI:              {summary['current_mtd_zsci']:+.3f} °C")
    print(
        f"MTD coverage:                  "
        f"{summary['mtd_days_available']}/{summary['mtd_days_in_month']} "
        f"({summary['mtd_coverage_fraction']:.1%})"
    )
    print(f"Latest OISST status:           {summary['latest_daily_oisst_status']}")
    print()
    print("STEP 3.2 COMPLETE ✅")


if __name__ == "__main__":
    main()

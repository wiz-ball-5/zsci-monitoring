from __future__ import annotations

import argparse
from pathlib import Path
import shutil


def copy_required(src: Path, dst: Path):
    if not src.exists():
        raise FileNotFoundError(f"Required source missing: {src}")
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    print(f"Copied: {src} -> {dst}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "step3_dir",
        help="Path to your corrected Step 3.3 project, e.g. ../zsci-monitoring-step3",
    )
    args = parser.parse_args()

    repo = Path(".").resolve()
    step3 = Path(args.step3_dir).resolve()

    if not step3.exists():
        raise SystemExit(f"Step 3 folder not found: {step3}")

    print("=" * 78)
    print("PREPARE STEP 5 RELEASE REPOSITORY")
    print("=" * 78)

    # Copy the exact scientific engine that produced the validated current ZSCI.
    copy_required(
        step3 / "src" / "zsci_monitoring",
        repo / "src" / "zsci_monitoring",
    )

    for name in ["run_step3.py", "run_step2.py", "download_hadisst.py"]:
        src = step3 / name
        if src.exists():
            copy_required(src, repo / name)

    # Fresh GitHub runners do not have the raw climatology NetCDF, so commit
    # this tiny validated 365-row climatology CSV.
    copy_required(
        step3 / "data" / "processed"
        / "oisst_zsci_daily_climatology_1981_2010.csv",
        repo / "data" / "processed"
        / "oisst_zsci_daily_climatology_1981_2010.csv",
    )

    meta = step3 / "data" / "metadata" / "hadisst_source.json"
    if meta.exists():
        copy_required(
            meta,
            repo / "data" / "metadata" / "hadisst_source.json",
        )

    required_public_data = [
        repo / "data/processed/hadisst_zsci_current_full.csv",
        repo / "data/processed/oisst_zsci_daily.csv",
        repo / "data/processed/oisst_zsci_monthly_monitor.csv",
        repo / "data/processed/current_zsci.json",
        repo / "data/processed/oisst_zsci_monthly_history.csv",
        repo / "data/processed/oisst_zsci_daily_climatology_1981_2010.csv",
    ]

    missing = [str(p) for p in required_public_data if not p.exists()]
    if missing:
        print("\nMissing release data:")
        for p in missing:
            print(" -", p)
        raise SystemExit(
            "\nFinish Step 4.1 and/or re-import Step 3 data before GitHub deployment."
        )

    # Ensure the deployed Step-3 engine is the corrected one.
    oisst_py = repo / "src/zsci_monitoring/oisst.py"
    code = oisst_py.read_text(encoding="utf-8")
    for marker in [
        "_decode_physical_climatology_sst",
        "validate_latest_scientific_sanity",
        "clim_raw_contrast",
    ]:
        if marker not in code:
            raise SystemExit(
                f"Scientific engine check failed: marker {marker!r} missing "
                f"from {oisst_py}"
            )

    print()
    print("Release repository preparation: PASS")
    print()
    print("Next:")
    print("  python -m pip install -r requirements.txt")
    print("  python validate_step41.py")
    print("  python -m pytest -q test_step41.py")
    print("  python smoke_deploy.py")


if __name__ == "__main__":
    main()

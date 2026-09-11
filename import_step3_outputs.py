from pathlib import Path
import argparse, shutil

REQUIRED = [
    "data/processed/hadisst_zsci_current_full.csv",
    "data/processed/oisst_zsci_daily.csv",
    "data/processed/oisst_zsci_monthly_monitor.csv",
    "data/processed/current_zsci.json",
]

parser = argparse.ArgumentParser()
parser.add_argument("step3_dir")
args = parser.parse_args()

src_root = Path(args.step3_dir).resolve()
dst_root = Path(".").resolve()

if not src_root.exists():
    raise SystemExit(f"Step 3 folder not found: {src_root}")

for rel in REQUIRED:
    src = src_root / rel
    if not src.exists():
        raise SystemExit(f"Required Step 3 output missing: {src}")
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print("Copied:", rel)

print("\nStep 3 outputs imported successfully ✅")

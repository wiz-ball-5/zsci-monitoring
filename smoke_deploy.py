from pathlib import Path
import importlib
import json

required = [
    Path("data/processed/hadisst_zsci_current_full.csv"),
    Path("data/processed/oisst_zsci_daily.csv"),
    Path("data/processed/oisst_zsci_monthly_monitor.csv"),
    Path("data/processed/current_zsci.json"),
    Path("data/processed/oisst_zsci_monthly_history.csv"),
    Path("data/processed/oisst_zsci_daily_climatology_1981_2010.csv"),
]

missing = [str(p) for p in required if not p.exists()]
if missing:
    raise SystemExit("Missing deployment data:\n" + "\n".join(missing))

current = json.loads(Path("data/processed/current_zsci.json").read_text())
print("Latest observation:", current["latest_observation_date"])
print("Current MTD ZSCI:", current["current_mtd_zsci"])

module = importlib.import_module("app")
assert hasattr(module, "server")
print("Dash server import: PASS")
print("DEPLOYMENT SMOKE TEST: PASS")

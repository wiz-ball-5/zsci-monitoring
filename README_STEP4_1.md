# ZSCI Monitoring — Step 4.1

This refinement adds five public-facing panels:

1. **Right now** — current year vs every year since 1982, with 1997 and 2015 highlighted by default.
2. **Near-real-time evolution** — existing daily / 7-day / MTD OISST view.
3. **Components** — East SSTA, West SSTA, and ZSCI = East − West.
4. **Recent monthly context** — OISST raw monthly, HadISST raw monthly, HadISST 5-month finalized, current MTD.
5. **Historical context** — full HadISST series, NCC ENSO windows, 10y / 25y / All controls.

## Important design choice

The all-year "Right now" panel is **monthly**, not daily, in Step 4.1.

Reason: canonical ZSCI v1.0 is a monthly index, and the official NOAA/PSL monthly
OISST archive can be processed exactly with a modest subset download. A
full-resolution 1982-present daily ZSCI archive would require much more gridded
data. The daily current-state view remains available in panel 02.

## Apply to an existing successful Step 4 folder

Stop `python app.py` first with Ctrl+C.

Unzip the patch inside `/mnt/d/zsci-monitoring-step4`:

```bash
cd /mnt/d/zsci-monitoring-step4
unzip -o zsci-step4.1-dashboard-refinement.zip
```

Install/update dependencies:

```bash
python -m pip install -r requirements.txt
```

Build the one-time OISST monthly historical archive:

```bash
python build_oisst_monthly_history.py
```

This downloads only:
- 5°S–5°N
- 120°E–290°E
- monthly OISST
- all available months

It saves:

```text
data/processed/oisst_zsci_monthly_history.csv
```

Validate all Step 4.1 science/data connections:

```bash
python validate_step41.py
```

Expected last line:

```text
RESULT: PASS
```

Run UI unit tests:

```bash
python -m pytest -q test_step41.py
```

Expected:

```text
4 passed
```

Start the dashboard:

```bash
python app.py
```

Open:

```text
http://127.0.0.1:8050
```

The Dash debug toolbar is disabled by default. If you intentionally want debug
mode for development:

```bash
ZSCI_DEBUG=1 python app.py
```

## If the monthly OISST file should be refreshed later

```bash
python build_oisst_monthly_history.py --refresh
```

Step 5 will automate monthly-history refresh separately from the daily OISST
update, so the large monthly subset does not need to be fetched every day.

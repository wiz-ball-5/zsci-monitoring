# ZSCI Monitoring — Step 5
## GitHub → Render → GitHub Actions

This kit turns the successful Step 4.1 project into a deployable repository.

Architecture:

```text
NOAA OISST daily ── GitHub Actions daily ──┐
                                            ├─ commit small CSV/JSON
Met Office HadISST ─ GitHub Actions monthly ┤
NOAA OISST monthly ─ GitHub Actions monthly ┘
                    ↓
                 GitHub main
                    ↓
          Render automatic deploy
                    ↓
          public *.onrender.com site
```

Raw NetCDF files are never committed.

## A. Apply this kit

Stop the local Dash server, then:

```bash
cd /mnt/d/zsci-monitoring-step4
unzip -o zsci-step5-deployment-kit.zip
```

Copy the exact corrected Step-3 scientific engine into the web repo:

```bash
python prepare_step5_repo.py ../zsci-monitoring-step3
```

Install and validate:

```bash
python -m pip install -r requirements.txt
python validate_step41.py
python -m pytest -q test_step41.py
python smoke_deploy.py
```

All must pass.

## B. What goes into GitHub

Commit:
- app.py, dashboard.py, assets/
- src/zsci_monitoring/
- small `data/processed/*.csv` / `*.json`
- `.github/workflows/`
- `render.yaml`

Do NOT commit:
- `data/raw/`
- NetCDF files
- `.venv/`
- output figures
- `.BROKEN_v03.*`

Check:

```bash
git status
```

If a very large NetCDF appears, stop before committing.

## C. Create GitHub repository

Create an empty repository in GitHub, for example `zsci-monitoring`.
Do not initialize it with extra files if this local folder already contains them.

Then:

```bash
git init
git branch -M main
git add .
git status
git commit -m "Initial ZSCI Monitoring v1.0"
```

Add the remote URL GitHub shows:

```bash
git remote add origin https://github.com/YOUR_USERNAME/zsci-monitoring.git
git push -u origin main
```

Never store a GitHub token inside project files.

## D. Test GitHub Actions

In GitHub:

`Actions` → `Update daily OISST` → `Run workflow`

Wait for a green check.

The monthly action downloads the full HadISST archive, so it can be tested after
the first public deploy if desired.

The daily workflow has:

```yaml
permissions:
  contents: write
```

so the built-in Actions token can commit updated CSV/JSON data.

Do not enable branch protection that blocks this bot until the workflow is proven.

## E. Deploy on Render

The repository includes `render.yaml`.

In Render:

1. New → Blueprint
2. Connect/select the GitHub repository
3. Render reads `render.yaml`
4. Confirm the service
5. Apply the Blueprint

Encoded configuration:

```text
Runtime: Python
Build: pip install -r requirements.txt
Start: gunicorn app:server --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
Plan: Free
Health check: /
Auto deploy: every commit
```

After a successful deployment Render provides an `onrender.com` address.

## F. Automatic updates

Daily action:
- scheduled 18:17 UTC every day
- updates OISST daily + MTD products
- validates science
- commits changed CSV/JSON

Monthly action:
- scheduled on the 12th at 19:43 UTC
- refreshes HadISST
- refreshes OISST monthly history
- validates science
- commits updated monthly products

Each data commit triggers Render's automatic deployment.

## G. Public-release polish included

- Footer now says `ZSCI Monitoring · v1.0`
- Historical chart opens at 1950-present
- `All` still exposes the full HadISST record
- Dash debug toolbar remains off by default

## H. Acceptance checklist

```text
validate_step41.py               PASS
test_step41.py                   PASS
smoke_deploy.py                  PASS
GitHub daily Action              green
Render deployment               green
Public URL                       opens
Current MTD                      matches local JSON
2026 / 1997 / 2015 comparison    works
Components                       East - West = ZSCI
```

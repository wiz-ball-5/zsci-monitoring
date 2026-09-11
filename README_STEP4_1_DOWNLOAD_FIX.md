# Step 4.1 monthly OISST download fix

The error:

`ChunkedEncodingError / IncompleteRead`

means the NOAA/PSL NCSS HTTP connection ended before the ~31 MB response
finished. It does not indicate an OISST or ZSCI calculation error.

This patch changes only the download layer.

Instead of one ~31 MB NCSS response, the equatorial Pacific is downloaded as
six longitude chunks:

- 120E–150E
- 150E–180E
- 180E–210E
- 210E–240E
- 240E–270E
- 270E–290E

Each chunk is only a few MB, has automatic retry/backoff, is structurally
validated, and is cached. If a later chunk fails, rerunning the command reuses
all completed chunks instead of starting the full download from zero.

## Apply

Stop any current Python process first, then inside your Step 4 directory:

```bash
cd /mnt/d/zsci-monitoring-step4
unzip -o zsci-step4.1-monthly-download-fix.zip
```

Delete only old partial files:

```bash
find data/raw/oisst_monthly -name "*.part" -delete
```

Do NOT delete valid chunk `.nc` files if they already exist.

Then rerun:

```bash
python build_oisst_monthly_history.py
```

After the build succeeds:

```bash
python validate_step41.py
python -m pytest -q test_step41.py
python app.py
```

If one small chunk still fails after all retries, simply rerun
`python build_oisst_monthly_history.py`; completed chunks are preserved.

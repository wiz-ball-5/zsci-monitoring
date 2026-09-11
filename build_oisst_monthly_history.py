"""
Build the monthly OISST ZSCI archive used by Step 4.1.

Why monthly for the "Right now" year-comparison panel?
------------------------------------------------------
Canonical ZSCI v1.0 is fundamentally a monthly index. A full-resolution
0.25° daily OISST archive for 1982-present would require downloading and
processing a very large amount of gridded data. For Step 4.1 we therefore use
the official NOAA/PSL MONTHLY OISST record for the Jan–Dec "this year vs every
year" comparison. The existing Step-3 daily OISST pipeline remains the source
for near-real-time daily/MTD monitoring.

This script downloads only the ZSCI equatorial-Pacific subset from NOAA/PSL
via NCSS, then saves a small CSV.
"""

from __future__ import annotations

from pathlib import Path
import json
import time

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import xarray as xr


NCSS_URL = (
    "https://psl.noaa.gov/thredds/ncss/grid/"
    "Datasets/noaa.oisst.v2.highres/sst.mon.mean.nc"
)

RAW = Path("data/raw/oisst_monthly/sst.mon.mean.zsci_subset.nc")
CHUNK_DIR = Path("data/raw/oisst_monthly/chunks")
LON_CHUNKS = [(120, 150), (150, 180), (180, 210), (210, 240), (240, 270), (270, 290)]
OUT = Path("data/processed/oisst_zsci_monthly_history.csv")
META = Path("data/processed/oisst_zsci_monthly_history.meta.json")

LAT = (-5.0, 5.0)
WEST = (120.0, 205.0)
EAST = (205.0, 290.0)
BASE = ("1981-01-01", "2010-12-31")


def session():
    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    a = HTTPAdapter(max_retries=retry)
    s.mount("https://", a)
    s.headers.update({"User-Agent": "ZSCI-Monitoring-Step4.1/1.0"})
    return s


def _validate_ncss_file(path):
    """Cheap structural check so a truncated/HTML response is never accepted."""
    ds = xr.open_dataset(path, mask_and_scale=False)
    try:
        if "sst" not in ds:
            raise RuntimeError(f"No sst variable in {path}")
        da = normalize_names(ds["sst"])
        if da.sizes.get("time", 0) < 400:
            raise RuntimeError(
                f"Unexpectedly short monthly record in {path}: "
                f"{da.sizes.get('time', 0)} time steps"
            )
        if da.sizes.get("lat", 0) == 0 or da.sizes.get("lon", 0) == 0:
            raise RuntimeError(f"Empty spatial subset in {path}")
    finally:
        ds.close()


def _download_one_chunk(west, east, path, force=False, max_attempts=6):
    """
    Download one longitude chunk.

    The original Step 4.1 request was ~31 MB and could die mid-stream with
    IncompleteRead/ChunkedEncodingError. Splitting into ~5 MB longitude chunks
    makes each NCSS response much more robust. Completed chunks are cached, so
    rerunning resumes at the chunk level.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and not force:
        try:
            _validate_ncss_file(path)
            print(f"  cached {west:03d}E–{east:03d}E: {path.name}")
            return
        except Exception:
            path.unlink(missing_ok=True)

    params = {
        "var": "sst",
        "north": LAT[1],
        "south": LAT[0],
        "west": west,
        "east": east,
        "horizStride": 1,
        "time": "all",
        "accept": "netCDF4",
    }

    tmp = path.with_suffix(path.suffix + ".part")
    tmp.unlink(missing_ok=True)

    for attempt in range(1, max_attempts + 1):
        print(
            f"  downloading {west:03d}E–{east:03d}E "
            f"(attempt {attempt}/{max_attempts})"
        )
        s = session()
        # Avoid transparent content encoding on a dynamically generated
        # NetCDF response; this makes byte counts easier to validate.
        s.headers.update({"Accept-Encoding": "identity"})

        try:
            with s.get(
                NCSS_URL,
                params=params,
                stream=True,
                timeout=(30, 300),
            ) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0) or 0)
                done = 0

                with tmp.open("wb") as f:
                    for chunk in r.iter_content(chunk_size=512 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        done += len(chunk)

                        if total:
                            print(
                                f"\r    {done/1024/1024:.1f} / "
                                f"{total/1024/1024:.1f} MB "
                                f"({100*done/total:.0f}%)",
                                end="",
                                flush=True,
                            )
                        else:
                            print(
                                f"\r    {done/1024/1024:.1f} MB",
                                end="",
                                flush=True,
                            )
                print()

                if total and done != total:
                    raise RuntimeError(
                        f"incomplete response: got {done} of {total} bytes"
                    )

            if not tmp.exists() or tmp.stat().st_size < 200_000:
                raise RuntimeError("downloaded chunk is unexpectedly small")

            _validate_ncss_file(tmp)
            tmp.replace(path)
            print(f"    saved {path.name}")
            return

        except Exception as exc:
            tmp.unlink(missing_ok=True)
            print(f"    attempt failed: {type(exc).__name__}: {exc}")

            if attempt == max_attempts:
                raise RuntimeError(
                    f"Could not download longitude chunk "
                    f"{west}E–{east}E after {max_attempts} attempts."
                ) from exc

            wait = min(30, 2 ** attempt)
            print(f"    retrying in {wait} s ...")
            time.sleep(wait)
        finally:
            s.close()


def _merge_chunks_to_raw(chunk_paths):
    """
    Merge cached physical-SST longitude chunks into the single subset file
    expected by the rest of the Step 4.1 calculation.
    """
    arrays = []
    for path in chunk_paths:
        arrays.append(physical_sst_from_ncss(path))

    combined = xr.concat(arrays, dim="lon").sortby("lon")

    # Drop any duplicate longitude cell that might appear at a chunk boundary.
    lon = np.asarray(combined["lon"].values)
    _, first_idx = np.unique(lon, return_index=True)
    first_idx = np.sort(first_idx)
    combined = combined.isel(lon=first_idx)

    combined = combined.astype("float32")
    combined.attrs = {
        "units": "degC",
        "long_name": "NOAA OISST monthly SST, ZSCI Pacific subset",
        "note": "Combined from cached NCSS longitude chunks; physical units.",
    }

    RAW.parent.mkdir(parents=True, exist_ok=True)
    tmp_raw = RAW.with_suffix(RAW.suffix + ".part")
    tmp_raw.unlink(missing_ok=True)

    combined.to_dataset(name="sst").to_netcdf(tmp_raw)
    _validate_ncss_file(tmp_raw)
    tmp_raw.replace(RAW)

    print(f"Merged {len(chunk_paths)} chunks into: {RAW}")


def download_subset(force=False):
    RAW.parent.mkdir(parents=True, exist_ok=True)
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)

    # Clean the partial file left by the old single-request downloader.
    RAW.with_suffix(RAW.suffix + ".part").unlink(missing_ok=True)

    if RAW.exists() and not force:
        try:
            _validate_ncss_file(RAW)
            print(f"Using cached monthly OISST subset: {RAW}")
            return
        except Exception:
            print("Cached combined monthly subset is invalid; rebuilding it.")
            RAW.unlink(missing_ok=True)

    print("Downloading NOAA/PSL monthly OISST ZSCI subset...")
    print("Spatial subset: 5°S–5°N, 120°E–290°E; all available months.")
    print(
        "Robust mode: six small longitude chunks with automatic retry. "
        "Completed chunks are cached."
    )

    chunk_paths = []
    for west, east in LON_CHUNKS:
        path = CHUNK_DIR / f"sst.mon.mean.{west:03d}E-{east:03d}E.nc"
        _download_one_chunk(west, east, path, force=force)
        chunk_paths.append(path)

    _merge_chunks_to_raw(chunk_paths)

def normalize_names(da):
    rename = {}
    if "latitude" in da.dims:
        rename["latitude"] = "lat"
    if "longitude" in da.dims:
        rename["longitude"] = "lon"
    if rename:
        da = da.rename(rename)
    return da


def physical_sst_from_ncss(path):
    """
    Robustly handle NOAA/PSL packing metadata.

    We deliberately disable xarray's automatic scale/mask and decide whether
    the values are already physical °C or still packed. This prevents the
    100× scaling bug diagnosed in Step 3.
    """
    ds = xr.open_dataset(path, mask_and_scale=False)
    try:
        raw = normalize_names(ds["sst"]).astype("float64")

        for key in ("_FillValue", "missing_value"):
            if key in raw.attrs:
                try:
                    fv = float(np.asarray(raw.attrs[key]).ravel()[0])
                    raw = raw.where(raw != fv)
                except Exception:
                    pass

        scale = float(raw.attrs.get("scale_factor", 1.0))
        offset = float(raw.attrs.get("add_offset", 0.0))

        candidates = [
            ("already physical", raw),
            ("packed -> physical", raw * scale + offset),
        ]

        good = []
        for label, da in candidates:
            vals = np.asarray(da.values, dtype=float)
            vals = vals[np.isfinite(vals)]
            if vals.size == 0:
                continue
            q01, q50, q99 = np.nanpercentile(vals, [1, 50, 99])
            plausible = q01 > -5.5 and q99 < 42 and 10 < q50 < 35
            if plausible:
                good.append((label, da, (q01, q50, q99)))

        if not good:
            raise ValueError(
                f"Could not recover physical SST; scale_factor={scale}, add_offset={offset}"
            )

        # If both are plausible (normally scale=1), either is equivalent.
        label, sst, stats = good[0] if len(good) == 1 else good[-1]
        print(
            f"SST scaling check: {label}; percentiles "
            f"{stats[0]:.2f}, {stats[1]:.2f}, {stats[2]:.2f} °C"
        )
        return sst.load()
    finally:
        ds.close()


def area_mean(da, lon_bounds):
    lat_vals = da["lat"].values
    lat_slice = slice(-5, 5) if lat_vals[0] < lat_vals[-1] else slice(5, -5)
    sub = da.sel(
        lat=lat_slice,
        lon=slice(lon_bounds[0], lon_bounds[1]),
    )
    if sub.sizes.get("lat", 0) == 0 or sub.sizes.get("lon", 0) == 0:
        raise ValueError(f"Empty region selection for {lon_bounds}")
    w = np.cos(np.deg2rad(sub["lat"]))
    return sub.weighted(w).mean(("lat", "lon"), skipna=True)


def cosine5(series):
    w = np.array([1/12, 1/4, 1/3, 1/4, 1/12], dtype=float)
    return series.rolling(5, center=True).apply(
        lambda x: float(np.dot(x, w)),
        raw=True,
    )


def build(force_download=False):
    download_subset(force=force_download)
    sst = physical_sst_from_ncss(RAW)

    if "time" not in sst.dims:
        raise ValueError("Monthly OISST subset has no time dimension.")

    west = area_mean(sst, WEST)
    east = area_mean(sst, EAST)

    times = pd.to_datetime(sst["time"].values).to_period("M").to_timestamp()

    df = pd.DataFrame({
        "time": times,
        "west_sst": np.asarray(west.values, dtype=float),
        "east_sst": np.asarray(east.values, dtype=float),
    })
    df["raw_contrast"] = df["east_sst"] - df["west_sst"]
    df["month"] = df["time"].dt.month
    df["year"] = df["time"].dt.year

    base = df[
        (df["time"] >= pd.Timestamp(BASE[0]))
        & (df["time"] <= pd.Timestamp(BASE[1]))
    ].copy()

    clim = base.groupby("month").agg(
        west_clim_sst=("west_sst", "mean"),
        east_clim_sst=("east_sst", "mean"),
        clim_raw_contrast=("raw_contrast", "mean"),
        baseline_n=("raw_contrast", "count"),
    ).reset_index()

    df = df.merge(clim, on="month", how="left")
    df["west_ssta"] = df["west_sst"] - df["west_clim_sst"]
    df["east_ssta"] = df["east_sst"] - df["east_clim_sst"]
    df["zsci_monthly"] = df["raw_contrast"] - df["clim_raw_contrast"]
    df["zsci_from_components"] = df["east_ssta"] - df["west_ssta"]
    df["zsci_smoothed_5m"] = cosine5(df["zsci_monthly"])

    closure = float(
        np.nanmax(
            np.abs(df["zsci_monthly"] - df["zsci_from_components"])
        )
    )
    if closure > 1e-10:
        raise AssertionError(f"Monthly ZSCI component closure failed: {closure}")

    clim_vals = clim["clim_raw_contrast"]
    if float(clim_vals.median()) >= -0.5:
        raise AssertionError(
            "Monthly OISST climatological EAST-WEST contrast is not physically plausible."
        )

    base_zero = (
        df[
            (df["time"] >= pd.Timestamp(BASE[0]))
            & (df["time"] <= pd.Timestamp(BASE[1]))
        ]
        .groupby("month")["zsci_monthly"]
        .mean()
        .abs()
        .max()
    )
    if float(base_zero) > 1e-10:
        raise AssertionError(f"Baseline monthly means are not zero: {base_zero}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)

    meta = {
        "source": "NOAA/PSL OISST v2.1 high-resolution monthly mean",
        "ncss_url": NCSS_URL,
        "baseline": "1981-2010 available months",
        "east_box": "5S-5N, 205E-290E",
        "west_box": "5S-5N, 120E-205E",
        "spatial_weighting": "cos(latitude)",
        "first_month": df["time"].min().strftime("%Y-%m"),
        "latest_month": df["time"].max().strftime("%Y-%m"),
        "rows": len(df),
        "component_closure_max_abs_degC": closure,
    }
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Saved monthly history: {OUT}")
    print(f"Months: {meta['first_month']} through {meta['latest_month']}")
    print(
        "Monthly climatological EAST-WEST contrast: "
        f"{clim_vals.min():+.3f} to {clim_vals.max():+.3f} °C"
    )
    print(f"Component closure max error: {closure:.3e} °C")
    print("RESULT: PASS")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    build(force_download=args.refresh)

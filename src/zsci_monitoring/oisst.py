"""
Near-real-time ZSCI monitoring from NOAA OISST v2.1 — corrected Step 3.2.

Canonical ZSCI v1.0 measures the anomalous EAST-minus-WEST SST contrast.
For daily monitoring:

    raw_contrast(day) = mean_SST_EAST(day) - mean_SST_WEST(day)

    ZSCI_daily(day) =
        raw_contrast(day)
        - climatological_raw_contrast_1981_2010(day_of_year)

where the daily climatological contrast is built once from NOAA/PSL's
official 1981–2010 OISST daily long-term-mean file.

MTD ZSCI is the arithmetic mean of available daily ZSCI values in the
current month.

Important:
- Daily / MTD values are provisional monitoring products.
- They are NOT the manuscript's centered 5-month-smoothed monthly ZSCI.
- Preliminary NCEI OISST files are replaced with final files when available.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import calendar
import json
import shutil

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import xarray as xr

from .zsci import SPEC, area_mean


# NOAA/PSL official 1981–2010 DAILY long-term mean.
#
# Step 3.2a uses THREDDS NetCDF Subset Service (NCSS) so we download only
# the equatorial-Pacific region needed by ZSCI rather than the 47 MB global file.
PSL_DAILY_CLIM_NCSS = (
    "https://psl.noaa.gov/thredds/ncss/grid/"
    "Datasets/noaa.oisst.v2.derived/sst.day.1981-2010.ltm.nc"
)

# Full-file mirrors are retained only as fallbacks.
PSL_DAILY_CLIM_FULL_URLS = [
    (
        "https://downloads.psl.noaa.gov/"
        "Datasets/noaa.oisst.v2.derived/sst.day.1981-2010.ltm.nc"
    ),
    (
        "https://psl.noaa.gov/thredds/fileServer/"
        "Datasets/noaa.oisst.v2.derived/sst.day.1981-2010.ltm.nc"
    ),
]

# Primary near-real-time OISST archive.
NCEI_DIRECT_BASE = (
    "https://www.ncei.noaa.gov/data/"
    "sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr"
)

# Fallback when the plain HTTPS archive is temporarily unavailable.
NCEI_THREDDS_BASE = (
    "https://www.ncei.noaa.gov/thredds/fileServer/"
    "OisstBase/NetCDF/V2.1/AVHRR"
)

DEFAULT_INITIAL_LOOKBACK_DAYS = 120
DEFAULT_REVISION_WINDOW_DAYS = 21


@dataclass(frozen=True)
class OISSTDailyFile:
    day: date
    status: str
    url: str
    filename: str


def _requests_session() -> requests.Session:
    session = requests.Session()
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
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {"User-Agent": "ZSCI-Monitoring/0.3.3 scientific-research"}
    )
    return session


def _stream_to_file(
    session: requests.Session,
    url: str,
    destination: Path,
    *,
    params: dict | None = None,
    label: str = "download",
) -> str:
    """Stream a file with visible progress so a slow NOAA response is not opaque."""
    tmp = destination.with_suffix(destination.suffix + ".part")
    if tmp.exists():
        tmp.unlink()

    with session.get(
        url,
        params=params,
        stream=True,
        timeout=(30, 300),
    ) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", "0") or 0)
        downloaded = 0

        with tmp.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)

                if total:
                    pct = 100.0 * downloaded / total
                    print(
                        f"\r  {label}: {downloaded/1024/1024:.1f} / "
                        f"{total/1024/1024:.1f} MB ({pct:.0f}%)",
                        end="",
                        flush=True,
                    )
                else:
                    print(
                        f"\r  {label}: {downloaded/1024/1024:.1f} MB",
                        end="",
                        flush=True,
                    )
        print()

    if tmp.stat().st_size < 200_000:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            "Downloaded climatology subset is suspiciously small; "
            "NOAA may have returned an error document."
        )

    tmp.replace(destination)
    return str(r.url)


def _download_required(
    urls: list[str],
    destination: Path,
    force: bool = False,
) -> str:
    """
    Download the required NOAA/PSL climatology.

    Step 3.2a first asks PSL NCSS for only:
      5°S–5°N, 120°E–290°E, all 365 climatological days.

    This is only a few MB instead of downloading the 47 MB global file.
    """
    if destination.exists() and not force:
        return "cached"

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".part")
    if tmp.exists():
        tmp.unlink()

    session = _requests_session()
    errors = []

    try:
        params = {
            "var": "sst",
            "north": SPEC.lat_max,
            "south": SPEC.lat_min,
            "west": SPEC.west_lon_min,
            "east": SPEC.east_lon_max,
            "horizStride": 1,
            "time": "all",
            "accept": "netCDF4",
        }

        print("Requesting only the ZSCI equatorial-Pacific subset from NOAA/PSL NCSS...")
        try:
            used = _stream_to_file(
                session,
                PSL_DAILY_CLIM_NCSS,
                destination,
                params=params,
                label="climatology subset",
            )

            # Validate the subset immediately.
            ds = xr.open_dataset(destination, decode_times=False)
            try:
                if "sst" not in ds:
                    raise RuntimeError(
                        f"NCSS file has no SST variable: {list(ds.data_vars)}"
                    )
                da = ds["sst"]
                if da.sizes.get("time", 0) != 365:
                    raise RuntimeError(
                        f"Expected 365 climatology days; got {da.sizes.get('time', 0)}"
                    )
                if da.sizes.get("lat", 0) == 0 or da.sizes.get("lon", 0) == 0:
                    raise RuntimeError("NCSS returned an empty spatial subset.")
            finally:
                ds.close()

            print(f"Validated NOAA/PSL subset: {destination}")
            return used
        except Exception as exc:
            errors.append(f"NCSS subset: {exc}")
            destination.unlink(missing_ok=True)
            print(f"NCSS subset failed: {exc}")
            print("Falling back to the official full-file mirrors...")

        # Only if NCSS is unavailable do we try the original global files.
        for url in urls:
            print(f"Trying fallback: {url}")
            try:
                return _stream_to_file(
                    session,
                    url,
                    destination,
                    label="full climatology",
                )
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                destination.unlink(missing_ok=True)
    finally:
        session.close()

    raise RuntimeError(
        "Could not download the NOAA/PSL daily climatology.\n"
        + "\n".join(errors)
    )

def _normalize_sst(da: xr.DataArray) -> xr.DataArray:
    rename = {}
    if "latitude" in da.dims:
        rename["latitude"] = "lat"
    if "longitude" in da.dims:
        rename["longitude"] = "lon"
    if rename:
        da = da.rename(rename)

    for dim in ("zlev", "depth"):
        if dim in da.dims and da.sizes[dim] == 1:
            da = da.isel({dim: 0}, drop=True)

    return da


def _decode_physical_climatology_sst(raw: xr.DataArray) -> xr.DataArray:
    """
    Robustly recover physical SST (degC) from a PSL climatology file.

    Why this is needed:
    -------------------
    The original PSL file is packed Int16 with scale_factor=0.01. In the
    NCSS subset returned by PSL, the numeric values may already be unpacked
    to physical degC while the scale_factor metadata is still retained.
    If xarray auto-applies that stale scale factor again, 29 °C becomes
    0.29 °C.

    This function opens data with mask_and_scale=False and chooses between:
      A) raw values as already-physical SST, or
      B) raw * scale_factor + add_offset

    using conservative physical plausibility checks.
    """
    da = _normalize_sst(raw)

    # Mask explicit fill/missing values before evaluating candidates.
    fill_values = []
    for key in ("_FillValue", "missing_value"):
        value = da.attrs.get(key)
        if value is not None:
            try:
                fill_values.append(float(np.asarray(value).ravel()[0]))
            except Exception:
                pass

    work = da.astype("float64")
    for fv in fill_values:
        work = work.where(work != fv)

    scale = float(da.attrs.get("scale_factor", 1.0))
    offset = float(da.attrs.get("add_offset", 0.0))

    raw_candidate = work
    scaled_candidate = work * scale + offset

    def score(candidate: xr.DataArray) -> tuple[bool, dict]:
        vals = np.asarray(candidate.values, dtype=float)
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            return False, {}

        q01, q50, q99 = np.nanpercentile(vals, [1, 50, 99])
        # SST climatology in this tropical-Pacific subset should be in degC.
        plausible = (
            q01 > -5.5
            and q99 < 42.0
            and 10.0 < q50 < 35.0
        )
        return plausible, {
            "q01": float(q01),
            "q50": float(q50),
            "q99": float(q99),
        }

    raw_ok, raw_stats = score(raw_candidate)
    scaled_ok, scaled_stats = score(scaled_candidate)

    if raw_ok and not scaled_ok:
        print(
            "PSL NCSS scaling check: using numeric values as already-unpacked "
            "physical SST (degC)."
        )
        print(
            f"  raw SST percentiles: "
            f"{raw_stats['q01']:.2f}, {raw_stats['q50']:.2f}, "
            f"{raw_stats['q99']:.2f} °C"
        )
        return raw_candidate

    if scaled_ok and not raw_ok:
        print(
            "PSL packing check: applying scale_factor/add_offset to recover "
            "physical SST (degC)."
        )
        print(
            f"  unpacked SST percentiles: "
            f"{scaled_stats['q01']:.2f}, {scaled_stats['q50']:.2f}, "
            f"{scaled_stats['q99']:.2f} °C"
        )
        return scaled_candidate

    if raw_ok and scaled_ok:
        # This occurs for normal scale_factor=1. Prefer the mathematically
        # decoded candidate, which is equivalent in that case.
        print("PSL scaling check: both representations are physically plausible.")
        return scaled_candidate

    raise ValueError(
        "Could not recover physically plausible SST from PSL climatology. "
        f"raw_stats={raw_stats}, scaled_stats={scaled_stats}, "
        f"scale_factor={scale}, add_offset={offset}"
    )


def _load_climatology_sst_physical(source_nc: str | Path) -> xr.DataArray:
    """
    Load the climatology with xarray's automatic mask/scale disabled, then
    recover physical degC robustly. Data are loaded into memory before close.
    """
    ds = xr.open_dataset(
        source_nc,
        decode_times=False,
        mask_and_scale=False,
    )
    try:
        if "sst" not in ds:
            raise KeyError(
                f"Climatology file has no 'sst'. Variables: {list(ds.data_vars)}"
            )
        physical = _decode_physical_climatology_sst(ds["sst"]).load()
        return physical
    finally:
        ds.close()

def _climatology_sanity(df: pd.DataFrame) -> None:
    required = {
        "month", "day", "west_clim_sst",
        "east_clim_sst", "clim_raw_contrast"
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Daily climatology CSV missing columns: {sorted(missing)}")

    if len(df) != 365:
        raise ValueError(f"Expected 365 climatology days; found {len(df)}")

    c = pd.to_numeric(df["clim_raw_contrast"], errors="coerce")
    if not np.isfinite(c).all():
        raise ValueError("Daily climatological contrast contains NaN/inf")

    # This specifically catches the Step-3.0/3.1 failure where all values
    # silently became exactly zero.
    if float(np.nanmax(np.abs(c.values))) < 0.5:
        raise ValueError(
            "OISST climatological EAST-WEST contrast is implausibly close "
            "to zero. Refusing to calculate ZSCI."
        )

    # Tropical Pacific climatological EAST-WEST contrast should be negative:
    # WEST is warmer than EAST in the mean state.
    if float(np.nanmedian(c.values)) >= -0.5:
        raise ValueError(
            "Median climatological EAST-WEST contrast is not sufficiently "
            "negative. Check region extraction before proceeding."
        )


def build_daily_climatology(
    output_csv: str | Path = (
        "data/processed/oisst_zsci_daily_climatology_1981_2010.csv"
    ),
    source_nc: str | Path = (
        "data/raw/oisst_climatology/sst.day.1981-2010.ltm.nc"
    ),
    force: bool = False,
    refresh_source: bool = False,
) -> pd.DataFrame:
    """
    Build 365 daily climatological EAST-WEST contrasts from NOAA/PSL.

    We intentionally read the precomputed 1981–2010 LTM file instead of
    remotely averaging a multi-gigabyte monthly archive.
    """
    output_csv = Path(output_csv)
    source_nc = Path(source_nc)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if output_csv.exists() and not force:
        existing = pd.read_csv(output_csv)
        try:
            _climatology_sanity(existing)
            print(f"Valid OISST daily climatology already exists: {output_csv}")
            return existing
        except Exception as exc:
            print(f"Existing climatology failed validation: {exc}")
            print("It will be rebuilt.")

    print("Downloading/using NOAA/PSL 1981–2010 daily OISST climatology...")
    source_url = _download_required(
        PSL_DAILY_CLIM_FULL_URLS,
        source_nc,
        force=refresh_source,
    )

    # Do not decode the climatology's artificial time axis. Its 365 records
    # are ordered Jan 1 ... Dec 31; map them to a normal non-leap reference year.
    #
    # IMPORTANT: use mask_and_scale=False internally because PSL NCSS can return
    # already-unpacked values while retaining scale_factor=0.01 metadata.
    sst = _load_climatology_sst_physical(source_nc)

    if "time" not in sst.dims:
        raise ValueError(f"Expected time dimension. Dims: {sst.dims}")
    if sst.sizes["time"] != 365:
        raise ValueError(
            f"Expected 365 daily climatology records; got {sst.sizes['time']}"
        )

    west = area_mean(
        sst,
        (SPEC.lat_min, SPEC.lat_max),
        (SPEC.west_lon_min, SPEC.west_lon_max),
    )
    east = area_mean(
        sst,
        (SPEC.lat_min, SPEC.lat_max),
        (SPEC.east_lon_min, SPEC.east_lon_max),
    )

    ref_dates = pd.date_range("2001-01-01", periods=365, freq="D")
    out = pd.DataFrame(
        {
            "day_of_year": np.arange(1, 366),
            "month": ref_dates.month,
            "day": ref_dates.day,
            "west_clim_sst": np.asarray(west.values, dtype=float),
            "east_clim_sst": np.asarray(east.values, dtype=float),
        }
    )
    out["clim_raw_contrast"] = (
        out["east_clim_sst"] - out["west_clim_sst"]
    )
    out["baseline"] = "1981-2010"
    out["source"] = (
        source_url if source_url != "cached"
        else "cached NOAA/PSL sst.day.1981-2010.ltm.nc"
    )

    _climatology_sanity(out)
    out.to_csv(output_csv, index=False)

    print(f"Saved valid daily climatology: {output_csv}")
    print(
        "Climatological EAST-WEST contrast range: "
        f"{out['clim_raw_contrast'].min():+.3f} to "
        f"{out['clim_raw_contrast'].max():+.3f} °C"
    )
    return out


def climatology_for_date(day: date, climatology: pd.DataFrame) -> dict:
    """Return daily climatology; Feb 29 is interpolated from Feb 28/Mar 1."""
    if day.month == 2 and day.day == 29:
        a = climatology[
            (climatology["month"] == 2) & (climatology["day"] == 28)
        ].iloc[0]
        b = climatology[
            (climatology["month"] == 3) & (climatology["day"] == 1)
        ].iloc[0]
        return {
            "west_clim_sst": 0.5 * (a["west_clim_sst"] + b["west_clim_sst"]),
            "east_clim_sst": 0.5 * (a["east_clim_sst"] + b["east_clim_sst"]),
            "clim_raw_contrast": 0.5
            * (a["clim_raw_contrast"] + b["clim_raw_contrast"]),
        }

    row = climatology[
        (climatology["month"] == day.month)
        & (climatology["day"] == day.day)
    ]
    if len(row) != 1:
        raise ValueError(f"No unique climatology row for {day.month:02d}-{day.day:02d}")
    r = row.iloc[0]
    return {
        "west_clim_sst": float(r["west_clim_sst"]),
        "east_clim_sst": float(r["east_clim_sst"]),
        "clim_raw_contrast": float(r["clim_raw_contrast"]),
    }


def monitoring_zsci(
    raw_contrast: float,
    day: date,
    climatology: pd.DataFrame,
) -> tuple[float, dict]:
    clim = climatology_for_date(day, climatology)
    z = float(raw_contrast - clim["clim_raw_contrast"])
    return z, clim


def _daily_filename(day: date, preliminary: bool) -> str:
    stamp = day.strftime("%Y%m%d")
    suffix = "_preliminary" if preliminary else ""
    return f"oisst-avhrr-v02r01.{stamp}{suffix}.nc"


def _daily_url(
    day: date,
    preliminary: bool,
    base: str = NCEI_DIRECT_BASE,
) -> str:
    ym = day.strftime("%Y%m")
    return f"{base}/{ym}/{_daily_filename(day, preliminary)}"


def _download_if_exists(
    session: requests.Session,
    url: str,
    destination: Path,
    timeout=(20, 180),
) -> bool:
    tmp = destination.with_suffix(destination.suffix + ".part")
    if tmp.exists():
        tmp.unlink()

    with session.get(url, stream=True, timeout=timeout) as response:
        if response.status_code == 404:
            return False
        response.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    tmp.replace(destination)
    return True


def _try_download_sources(
    session: requests.Session,
    day: date,
    preliminary: bool,
    destination: Path,
) -> tuple[bool, str | None]:
    primary = _daily_url(day, preliminary, NCEI_DIRECT_BASE)
    try:
        if _download_if_exists(session, primary, destination):
            return True, primary
        return False, None
    except requests.RequestException as primary_exc:
        fallback = _daily_url(day, preliminary, NCEI_THREDDS_BASE)
        print(
            f"\n  Direct NCEI access failed for {day}; trying THREDDS fallback..."
        )
        try:
            if _download_if_exists(session, fallback, destination):
                return True, fallback
            return False, None
        except requests.RequestException as fallback_exc:
            raise requests.RequestException(
                f"Both NCEI routes failed. Direct: {primary_exc}; "
                f"THREDDS: {fallback_exc}"
            ) from fallback_exc


def acquire_daily_file(
    day: date,
    cache_dir: str | Path = "data/raw/oisst_daily",
    refresh_preliminary: bool = True,
    session: requests.Session | None = None,
) -> OISSTDailyFile | None:
    cache_dir = Path(cache_dir)
    session = session or _requests_session()

    final_path = (
        cache_dir / day.strftime("%Y") / _daily_filename(day, False)
    )
    prelim_path = (
        cache_dir / day.strftime("%Y") / _daily_filename(day, True)
    )

    if final_path.exists():
        return OISSTDailyFile(
            day, "final", _daily_url(day, False), str(final_path)
        )

    try:
        found, url = _try_download_sources(
            session, day, False, final_path
        )
        if found:
            if prelim_path.exists():
                prelim_path.unlink()
            return OISSTDailyFile(day, "final", url or "", str(final_path))
    except requests.RequestException as exc:
        print(f"\n  Warning: final download failed for {day}: {exc}")

    if prelim_path.exists() and not refresh_preliminary:
        return OISSTDailyFile(
            day, "preliminary", _daily_url(day, True), str(prelim_path)
        )

    try:
        found, url = _try_download_sources(
            session, day, True, prelim_path
        )
        if found:
            return OISSTDailyFile(
                day, "preliminary", url or "", str(prelim_path)
            )
    except requests.RequestException as exc:
        print(f"\n  Warning: preliminary download failed for {day}: {exc}")

    if prelim_path.exists():
        return OISSTDailyFile(
            day, "preliminary", _daily_url(day, True), str(prelim_path)
        )
    return None


def _normalize_daily_field(da: xr.DataArray) -> xr.DataArray:
    da = _normalize_sst(da)
    if "time" in da.dims and da.sizes["time"] == 1:
        da = da.isel(time=0, drop=True)
    return da


def _regional_contrast(da: xr.DataArray) -> tuple[float, float, float]:
    west = area_mean(
        da,
        (SPEC.lat_min, SPEC.lat_max),
        (SPEC.west_lon_min, SPEC.west_lon_max),
    )
    east = area_mean(
        da,
        (SPEC.lat_min, SPEC.lat_max),
        (SPEC.east_lon_min, SPEC.east_lon_max),
    )
    w = float(west.values)
    e = float(east.values)
    return w, e, e - w


def contrast_from_daily_file(path: str | Path) -> dict:
    path = Path(path)
    ds = xr.open_dataset(path)
    try:
        if "sst" not in ds:
            raise KeyError(f"OISST file has no 'sst': {list(ds.data_vars)}")

        sst = _normalize_daily_field(ds["sst"])
        west_sst, east_sst, raw = _regional_contrast(sst)

        native = np.nan
        if "anom" in ds:
            anom = _normalize_daily_field(ds["anom"])
            _, _, native = _regional_contrast(anom)

        return {
            "west_sst": west_sst,
            "east_sst": east_sst,
            "raw_contrast": raw,
            "native_anom_contrast_1971_2000": native,
        }
    finally:
        ds.close()


def choose_update_start(
    existing_daily_csv: str | Path,
    today: date,
    initial_lookback_days: int = DEFAULT_INITIAL_LOOKBACK_DAYS,
    revision_window_days: int = DEFAULT_REVISION_WINDOW_DAYS,
) -> date:
    path = Path(existing_daily_csv)
    fresh_start = today - timedelta(days=initial_lookback_days - 1)
    if not path.exists():
        return fresh_start

    try:
        old = pd.read_csv(path, parse_dates=["date"])
        if old.empty:
            return fresh_start
        latest = old["date"].max().date()
        revision_start = latest - timedelta(days=revision_window_days - 1)
        return max(fresh_start, revision_start)
    except Exception:
        return fresh_start


def backup_broken_v03_outputs(
    daily_csv: str | Path = "data/processed/oisst_zsci_daily.csv",
) -> bool:
    """
    Detect the exact Step-3.0/3.1 bug (zero climatological contrast).
    If found, back up bad processed products and force a full 120-day rebuild.
    """
    daily_csv = Path(daily_csv)
    if not daily_csv.exists():
        return False

    try:
        old = pd.read_csv(daily_csv)
    except Exception:
        return False

    if "clim_raw_contrast" not in old or old.empty:
        return False

    values = pd.to_numeric(old["clim_raw_contrast"], errors="coerce").dropna()
    if values.empty:
        return False

    broken = float(values.abs().median()) < 0.1
    if not broken:
        return False

    print()
    print("Detected broken Step-3.0/3.1 output: climatological contrast ≈ 0.")
    print("Backing it up and rebuilding from cached NOAA daily files.")

    targets = [
        Path("data/processed/oisst_zsci_daily.csv"),
        Path("data/processed/oisst_zsci_monthly_monitor.csv"),
        Path("data/processed/current_zsci.json"),
        Path("data/processed/oisst_zsci_climatology_1981_2010.csv"),
    ]
    for target in targets:
        if target.exists():
            backup = target.with_name(
                target.stem + ".BROKEN_v03" + target.suffix
            )
            if backup.exists():
                backup.unlink()
            shutil.move(str(target), str(backup))
            print(f"  backup: {backup}")
    return True


def update_recent_daily_zsci(
    climatology: pd.DataFrame,
    output_csv: str | Path = "data/processed/oisst_zsci_daily.csv",
    cache_dir: str | Path = "data/raw/oisst_daily",
    today: date | None = None,
    initial_lookback_days: int = DEFAULT_INITIAL_LOOKBACK_DAYS,
) -> pd.DataFrame:
    _climatology_sanity(climatology)

    today = today or datetime.now(timezone.utc).date()
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    old = (
        pd.read_csv(output_csv, parse_dates=["date"])
        if output_csv.exists()
        else pd.DataFrame()
    )

    start = choose_update_start(
        output_csv,
        today=today,
        initial_lookback_days=initial_lookback_days,
    )
    days = [
        start + timedelta(days=i)
        for i in range((today - start).days + 1)
    ]

    print(f"Checking/reprocessing OISST from {start} through {today} ...")
    session = _requests_session()
    rows = []
    try:
        for i, day in enumerate(days, 1):
            print(
                f"\r  {i:3d}/{len(days):3d}  {day.isoformat()}",
                end="",
                flush=True,
            )
            info = acquire_daily_file(
                day,
                cache_dir=cache_dir,
                refresh_preliminary=True,
                session=session,
            )
            if info is None:
                continue

            vals = contrast_from_daily_file(info.filename)
            z, clim = monitoring_zsci(
                vals["raw_contrast"],
                day=day,
                climatology=climatology,
            )

            rows.append(
                {
                    "date": pd.Timestamp(day),
                    **vals,
                    **clim,
                    "zsci_daily_monitor": z,
                    "oisst_status": info.status,
                    "source_url": info.url,
                }
            )
    finally:
        print()
        session.close()

    new = pd.DataFrame(rows)
    if old.empty and new.empty:
        raise RuntimeError("No OISST daily data available.")

    if not old.empty:
        old["date"] = pd.to_datetime(old["date"])
    if not new.empty:
        new["date"] = pd.to_datetime(new["date"])

    if old.empty:
        merged = new
    elif new.empty:
        merged = old
    else:
        old = old.loc[~old["date"].isin(new["date"])]
        merged = pd.concat([old, new], ignore_index=True)

    merged = (
        merged.sort_values("date")
        .drop_duplicates("date", keep="last")
        .reset_index(drop=True)
    )
    merged.to_csv(output_csv, index=False)
    print(f"Saved corrected daily OISST ZSCI: {output_csv}")
    return merged


def build_monthly_monitor(
    daily: pd.DataFrame,
    output_csv: str | Path = "data/processed/oisst_zsci_monthly_monitor.csv",
) -> pd.DataFrame:
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["month_start"] = df["date"].dt.to_period("M").dt.to_timestamp()

    rows = []
    for month_start, g in df.groupby("month_start"):
        g = g.sort_values("date")
        days_in_month = calendar.monthrange(
            month_start.year, month_start.month
        )[1]
        days_available = int(g["date"].dt.day.nunique())
        complete = days_available == days_in_month

        statuses = set(g["oisst_status"].dropna().astype(str))
        if complete and statuses == {"final"}:
            status = "complete_final"
        elif complete:
            status = "complete_mixed"
        else:
            status = "month_to_date"

        rows.append(
            {
                "month": month_start,
                "zsci_monthly_or_mtd": float(
                    g["zsci_daily_monitor"].mean()
                ),
                "mean_raw_contrast": float(g["raw_contrast"].mean()),
                "mean_clim_raw_contrast": float(
                    g["clim_raw_contrast"].mean()
                ),
                "days_available": days_available,
                "days_in_month": days_in_month,
                "coverage_fraction": days_available / days_in_month,
                "latest_day": g["date"].max(),
                "contains_preliminary": bool(
                    (g["oisst_status"].astype(str) == "preliminary").any()
                ),
                "status": status,
            }
        )

    out = pd.DataFrame(rows).sort_values("month").reset_index(drop=True)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_csv, index=False)
    print(f"Saved corrected OISST monthly/MTD monitor: {output_csv}")
    return out


def validate_monitoring_identity(
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
    tolerance: float = 1e-12,
) -> float:
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["month"] = d["date"].dt.to_period("M").dt.to_timestamp()
    manual = (
        d.groupby("month")["zsci_daily_monitor"]
        .mean()
        .rename("manual")
        .reset_index()
    )
    m = monthly.copy()
    m["month"] = pd.to_datetime(m["month"])
    check = m.merge(manual, on="month", how="inner")
    err = float(
        np.nanmax(
            np.abs(
                check["zsci_monthly_or_mtd"].values
                - check["manual"].values
            )
        )
    )
    if err > tolerance:
        raise AssertionError(
            f"MTD identity failed: error={err}, tolerance={tolerance}"
        )
    return err


def validate_latest_scientific_sanity(daily: pd.DataFrame) -> None:
    """
    Catch failures that arithmetic-only tests cannot detect.
    """
    latest = daily.sort_values("date").iloc[-1]

    c = float(latest["clim_raw_contrast"])
    if c >= -0.5:
        raise AssertionError(
            f"Latest climatological EAST-WEST contrast is implausible: {c:+.3f} °C"
        )

    expected = float(latest["raw_contrast"] - c)
    actual = float(latest["zsci_daily_monitor"])
    if abs(expected - actual) > 1e-10:
        raise AssertionError("ZSCI does not equal raw contrast minus climatology.")

    native = float(
        latest.get("native_anom_contrast_1971_2000", np.nan)
    )
    if np.isfinite(native) and abs(native) > 1.0:
        # Different baselines can alter magnitude, but a strong +3 °C native
        # anomaly contrast should not become a large negative ZSCI.
        if np.sign(native) != np.sign(actual) and abs(actual) > 0.5:
            raise AssertionError(
                "Strong sign disagreement with NOAA's native anomaly contrast. "
                f"native={native:+.3f}, ZSCI1981-2010={actual:+.3f}"
            )


def write_current_summary(
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
    output_json: str | Path = "data/processed/current_zsci.json",
) -> dict:
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    m = monthly.copy()
    m["month"] = pd.to_datetime(m["month"])
    m["latest_day"] = pd.to_datetime(m["latest_day"])

    ld = d.sort_values("date").iloc[-1]
    lm = m.sort_values("month").iloc[-1]

    summary = {
        "index": "ZSCI",
        "product": "OISST near-real-time monitoring",
        "definition_version": SPEC.version,
        "daily_definition": (
            "daily OISST east-minus-west SST contrast minus NOAA/PSL "
            "1981-2010 daily climatological east-minus-west contrast"
        ),
        "baseline": "1981-2010",
        "latest_observation_date": ld["date"].date().isoformat(),
        "latest_daily_zsci": float(ld["zsci_daily_monitor"]),
        "latest_daily_oisst_status": str(ld["oisst_status"]),
        "latest_raw_contrast": float(ld["raw_contrast"]),
        "latest_climatological_contrast": float(ld["clim_raw_contrast"]),
        "latest_native_anom_contrast_1971_2000": (
            float(ld["native_anom_contrast_1971_2000"])
            if np.isfinite(ld["native_anom_contrast_1971_2000"])
            else None
        ),
        "current_month": lm["month"].strftime("%Y-%m"),
        "current_mtd_zsci": float(lm["zsci_monthly_or_mtd"]),
        "mtd_days_available": int(lm["days_available"]),
        "mtd_days_in_month": int(lm["days_in_month"]),
        "mtd_coverage_fraction": float(lm["coverage_fraction"]),
        "mtd_contains_preliminary": bool(lm["contains_preliminary"]),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Saved current summary: {output_json}")
    return summary

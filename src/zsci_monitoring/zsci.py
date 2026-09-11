"""
Canonical scientific implementation of ZSCI v1.0.

Definition copied from the manuscript/reproducibility notebook:

    ZSCI = anomaly of [mean SST(EAST) - mean SST(WEST)]

EAST : 5°S–5°N, 205°E–290°E (= 155°W–70°W)
WEST : 5°S–5°N, 120°E–205°E (= 120°E–155°W)

Monthly climatological baseline: 1981–2010
Spatial weighting: cos(latitude)
Temporal smoothing: centered 5-month cosine-bell
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
import xarray as xr


@dataclass(frozen=True)
class ZSCISpec:
    version: str = "1.0"
    baseline_start: str = "1981-01-01"
    baseline_end: str = "2010-12-31"
    lat_min: float = -5.0
    lat_max: float = 5.0
    west_lon_min: float = 120.0
    west_lon_max: float = 205.0
    east_lon_min: float = 205.0
    east_lon_max: float = 290.0
    smooth_window: int = 5
    units: str = "degC"


SPEC = ZSCISpec()


def guess_coord(ds: xr.Dataset, candidates: Iterable[str]) -> str:
    for name in candidates:
        if name in ds.coords or name in ds.dims:
            return name
    raise KeyError(
        f"None of {list(candidates)} found. "
        f"Coordinates={list(ds.coords)}, dimensions={list(ds.dims)}"
    )


def guess_var(ds: xr.Dataset, candidates: Iterable[str]) -> str:
    for name in candidates:
        if name in ds.data_vars:
            return name
    raise KeyError(
        f"None of {list(candidates)} found. Variables={list(ds.data_vars)}"
    )


def standardize_longitude(ds: xr.Dataset, lon_name: str) -> xr.Dataset:
    """Convert longitudes to 0–360 and sort them."""
    lon = ds[lon_name]
    lon_new = xr.where(lon < 0, lon % 360, lon)
    return ds.assign_coords({lon_name: lon_new}).sortby(lon_name)


def ensure_month_start(da: xr.DataArray, time_name: str = "time") -> xr.DataArray:
    """Normalize monthly timestamps to the first day of each month."""
    t = pd.to_datetime(da[time_name].values).to_period("M").to_timestamp()
    return da.assign_coords({time_name: t})


def area_mean(
    da: xr.DataArray,
    lat_bounds: tuple[float, float],
    lon_bounds: tuple[float, float],
    lat_name: str = "lat",
    lon_name: str = "lon",
) -> xr.DataArray:
    """Cos(latitude)-weighted regional mean, matching the manuscript notebook."""
    lat_vals = da[lat_name].values
    if lat_vals[0] < lat_vals[-1]:
        lat_slice = slice(min(lat_bounds), max(lat_bounds))
    else:
        lat_slice = slice(max(lat_bounds), min(lat_bounds))

    sub = da.sel(
        {
            lat_name: lat_slice,
            lon_name: slice(min(lon_bounds), max(lon_bounds)),
        }
    )

    if sub.sizes.get(lat_name, 0) == 0 or sub.sizes.get(lon_name, 0) == 0:
        raise ValueError(
            f"Empty regional selection: lat={lat_bounds}, lon={lon_bounds}. "
            "Check coordinate names and longitude convention."
        )

    weights = np.cos(np.deg2rad(sub[lat_name]))
    # This normalization is retained because it appears in the manuscript notebook.
    # xarray.weighted() would give the same regional mean without it.
    weights = weights / weights.mean()

    return sub.weighted(weights).mean((lat_name, lon_name), skipna=True)


def monthly_anomaly(
    da: xr.DataArray,
    baseline: tuple[str, str] = (SPEC.baseline_start, SPEC.baseline_end),
    time_name: str = "time",
) -> xr.DataArray:
    """Remove the monthly 1981–2010 climatological seasonal cycle."""
    da = ensure_month_start(da, time_name=time_name)
    base = da.sel({time_name: slice(*baseline)})
    if base.sizes.get(time_name, 0) == 0:
        raise ValueError(
            f"No data inside baseline period {baseline[0]} to {baseline[1]}."
        )

    clim = base.groupby(f"{time_name}.month").mean(time_name)
    result = da.groupby(f"{time_name}.month") - clim

    # Modern xarray may retain "month" as an auxiliary coordinate.
    # Dropping it changes no values and prevents alignment conflicts later.
    if "month" in result.coords:
        result = result.drop_vars("month")
    return result


def cosine_bell_weights(window: int = SPEC.smooth_window) -> np.ndarray:
    """
    Cosine-bell weights used in the manuscript notebook.

    window=5 -> [1/12, 1/4, 1/3, 1/4, 1/12]
    """
    if window < 1 or window % 2 == 0:
        raise ValueError("window must be a positive odd integer")

    idx = np.arange(window)
    w = 0.5 * (1 - np.cos(2 * np.pi * (idx + 1) / (window + 1)))
    return w / w.sum()


def cosine_bell_smooth(
    ts: xr.DataArray,
    window: int = SPEC.smooth_window,
    time_name: str = "time",
) -> xr.DataArray:
    """Centered cosine-bell smoothing, matching the notebook."""
    w = cosine_bell_weights(window)
    return (
        ts.rolling({time_name: window}, center=True)
        .construct("win")
        .dot(xr.DataArray(w, dims=["win"]))
        .dropna(time_name)
    )


def prepare_sst_dataarray(ds: xr.Dataset) -> xr.DataArray:
    """
    Detect SST coordinates/variable, convert longitude to 0–360,
    rename to time/lat/lon, normalize timestamps, and handle centi-degree files.
    """
    time_name = guess_coord(ds, ["time", "TIME", "t", "valid_time"])
    lat_name = guess_coord(ds, ["lat", "latitude", "LAT", "y"])
    lon_name = guess_coord(ds, ["lon", "longitude", "LON", "x"])
    var_name = guess_var(ds, ["sst", "tos", "SST", "sea_surface_temperature"])

    ds = standardize_longitude(ds, lon_name)
    da = ds[var_name]

    rename = {}
    if time_name != "time":
        rename[time_name] = "time"
    if lat_name != "lat":
        rename[lat_name] = "lat"
    if lon_name != "lon":
        rename[lon_name] = "lon"
    if rename:
        da = da.rename(rename)

    da = ensure_month_start(da)

    sample = da.isel(time=slice(0, min(120, da.sizes["time"]))).values
    q99 = float(np.nanpercentile(sample, 99))
    if q99 > 100:
        da = da / 100.0

    return da


def compute_zsci(
    sst: xr.DataArray,
    baseline: tuple[str, str] = (SPEC.baseline_start, SPEC.baseline_end),
) -> xr.Dataset:
    """
    Compute ZSCI v1.0 from MONTHLY SST.

    Important:
    ---------
    This function calculates on exactly the time range provided to it.
    Therefore, for exact manuscript Figure 1 reproduction, first subset SST
    to 1950-01 through 2023-12 and then call this function. This preserves
    the notebook's centered-smoothing edge behavior.
    """
    sst = ensure_month_start(sst)

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

    raw_contrast = east - west
    zsci = monthly_anomaly(raw_contrast, baseline=baseline)
    zsci_smoothed = cosine_bell_smooth(zsci, window=SPEC.smooth_window)

    # Use outer alignment so raw monthly ZSCI is retained at the first/last two
    # months while the centered smoothed series is NaN there.
    out = xr.Dataset(
        {
            "west_sst": west,
            "east_sst": east,
            "raw_contrast": raw_contrast,
            "zsci": zsci,
            "zsci_smoothed": zsci_smoothed,
        }
    )

    out.attrs.update(
        {
            "index_name": "Zonal SST Contrast Index",
            "index_short_name": "ZSCI",
            "version": SPEC.version,
            "definition": "monthly anomaly of EAST mean SST minus WEST mean SST",
            "baseline": "1981-2010",
            "east_box": "5S-5N, 155W-70W",
            "west_box": "5S-5N, 120E-155W",
            "spatial_weighting": "cos(latitude)",
            "smoothing": "centered 5-month cosine-bell",
            "units": SPEC.units,
        }
    )
    return out

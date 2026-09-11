"""
Independent legacy path matching Cells 2–4 of the user's manuscript notebook.

This module is intentionally redundant. It exists only for Step 2 validation:
the refactored ZSCI core must reproduce this legacy calculation numerically.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

TIME_RANGE = ("1950-01-01", "2023-12-31")
BASE_PERIOD = ("1981-01-01", "2010-12-31")
SMOOTH_WIN = 5
WEST = {"lat": (-5, 5), "lon": (120, 205)}
EAST = {"lat": (-5, 5), "lon": (205, 290)}


def _guess_coord(ds, candidates):
    for c in candidates:
        if c in ds.coords or c in ds.dims:
            return c
    raise KeyError(f"None of {candidates} found. Available: {list(ds.coords)}")


def _guess_var(ds, candidates):
    for v in candidates:
        if v in ds.data_vars:
            return v
    raise KeyError(f"None of {candidates} found. Available: {list(ds.data_vars)}")


def _standardize_lon_ds(ds, lon_name):
    lon = ds[lon_name]
    lon_new = xr.where(lon < 0, lon % 360, lon)
    return ds.assign_coords({lon_name: lon_new}).sortby(lon_name)


def _ensure_month_start(da):
    t = pd.to_datetime(da.time.values).to_period("M").to_timestamp()
    return da.assign_coords(time=t)


def _area_mean(da, lat_name="lat", lon_name="lon", lat_b=None, lon_b=None):
    lat_vals = da[lat_name].values
    lat_slice = (
        slice(min(lat_b), max(lat_b))
        if lat_vals[0] < lat_vals[-1]
        else slice(max(lat_b), min(lat_b))
    )
    sub = da.sel(
        {
            lat_name: lat_slice,
            lon_name: slice(min(lon_b), max(lon_b)),
        }
    )
    weights = np.cos(np.deg2rad(sub[lat_name]))
    weights = weights / weights.mean()
    return sub.weighted(weights).mean((lat_name, lon_name), skipna=True)


def _monthly_anomaly(da, base=BASE_PERIOD, tdim="time"):
    da = _ensure_month_start(da)
    clim = da.sel({tdim: slice(*base)}).groupby(f"{tdim}.month").mean(tdim)
    out = da.groupby(f"{tdim}.month") - clim
    if "month" in out.coords:
        out = out.drop_vars("month")
    return out


def _cosine_bell_smooth(ts, window=5, tdim="time"):
    idx = np.arange(window)
    w = 0.5 * (1 - np.cos(2 * np.pi * (idx + 1) / (window + 1)))
    w = w / w.sum()
    return (
        ts.rolling({tdim: window}, center=True)
        .construct("win")
        .dot(xr.DataArray(w, dims=["win"]))
        .dropna(tdim)
    )


def legacy_compute_zsci(path):
    ds = xr.open_dataset(path)
    tn = _guess_coord(ds, ["time", "TIME", "t", "valid_time"])
    ln = _guess_coord(ds, ["lat", "latitude", "LAT", "y"])
    on = _guess_coord(ds, ["lon", "longitude", "LON", "x"])
    vn = _guess_var(ds, ["sst", "tos", "SST", "sea_surface_temperature"])

    ds = _standardize_lon_ds(ds, on)
    da = ds[vn]

    rename_dict = {}
    if tn != "time":
        rename_dict[tn] = "time"
    if ln != "lat":
        rename_dict[ln] = "lat"
    if on != "lon":
        rename_dict[on] = "lon"
    if rename_dict:
        da = da.rename(rename_dict)

    da = _ensure_month_start(da)

    q99 = float(
        np.nanpercentile(
            da.isel(time=slice(0, min(120, da.time.size))).values,
            99,
        )
    )
    if q99 > 100:
        da = da / 100.0

    # Critical manuscript behavior: subset BEFORE smoothing.
    da = da.sel(time=slice(*TIME_RANGE))

    west = _area_mean(da, "lat", "lon", WEST["lat"], WEST["lon"])
    east = _area_mean(da, "lat", "lon", EAST["lat"], EAST["lon"])
    raw_zsci = east - west
    anom_zsci = _monthly_anomaly(raw_zsci)
    sm_zsci = _cosine_bell_smooth(anom_zsci, SMOOTH_WIN)

    ds.close()
    return anom_zsci, sm_zsci

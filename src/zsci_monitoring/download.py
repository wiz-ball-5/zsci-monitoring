"""Official HadISST1 downloader."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import gzip
import hashlib
import json
import shutil

import requests
import xarray as xr

HADISST_FULL_URL = (
    "https://www.metoffice.gov.uk/hadobs/hadisst/data/HadISST_sst.nc.gz"
)


def _sha256(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(block_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _decompress_maybe_gzip(src: Path, dst: Path) -> None:
    """
    Met Office notes that some clients may leave a .gz suffix on an already
    uncompressed file, so detect gzip by magic bytes rather than suffix alone.
    """
    with src.open("rb") as f:
        magic = f.read(2)

    tmp = dst.with_suffix(dst.suffix + ".part")
    if tmp.exists():
        tmp.unlink()

    if magic == b"\x1f\x8b":
        with gzip.open(src, "rb") as fin, tmp.open("wb") as fout:
            shutil.copyfileobj(fin, fout, length=1024 * 1024)
    else:
        shutil.copyfile(src, tmp)

    tmp.replace(dst)


def inspect_hadisst(path: Path) -> dict:
    ds = xr.open_dataset(path)
    time_name = "time" if "time" in ds.coords else list(ds.coords)[0]
    latest = str(ds[time_name].values[-1])
    first = str(ds[time_name].values[0])
    vars_ = list(ds.data_vars)
    dims_ = {k: int(v) for k, v in ds.sizes.items()}
    ds.close()
    return {
        "first_time": first,
        "latest_time": latest,
        "variables": vars_,
        "dimensions": dims_,
    }


def download_hadisst(
    data_dir: str | Path = "data/raw",
    metadata_dir: str | Path = "data/metadata",
    refresh: bool = False,
) -> Path:
    data_dir = Path(data_dir)
    metadata_dir = Path(metadata_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    gz_path = data_dir / "HadISST_sst.nc.gz"
    nc_path = data_dir / "HadISST_sst.nc"
    metadata_path = metadata_dir / "hadisst_source.json"

    if nc_path.exists() and not refresh:
        info = inspect_hadisst(nc_path)
        print(f"HadISST already present: {nc_path}")
        print(f"Latest month in local file: {info['latest_time']}")
        print("Use --refresh when you want to re-download the official archive.")
        return nc_path

    print("Downloading official HadISST1 archive from Met Office...")
    print(HADISST_FULL_URL)
    print("The compressed archive is large (about 240 MB), so this can take a while.")

    tmp_gz = gz_path.with_suffix(gz_path.suffix + ".part")
    if tmp_gz.exists():
        tmp_gz.unlink()

    with requests.get(
        HADISST_FULL_URL,
        stream=True,
        timeout=(30, 300),
        headers={"User-Agent": "ZSCI-Monitoring/0.2 scientific research"},
    ) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0

        with tmp_gz.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = 100 * downloaded / total
                    print(
                        f"\rDownloaded {downloaded/1024/1024:.1f} / "
                        f"{total/1024/1024:.1f} MB ({pct:.1f}%)",
                        end="",
                        flush=True,
                    )
                else:
                    print(
                        f"\rDownloaded {downloaded/1024/1024:.1f} MB",
                        end="",
                        flush=True,
                    )
        print()

        response_headers = {
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
            "content_length": response.headers.get("content-length"),
        }

    tmp_gz.replace(gz_path)

    print("Decompressing...")
    _decompress_maybe_gzip(gz_path, nc_path)

    print("Validating NetCDF...")
    info = inspect_hadisst(nc_path)

    meta = {
        "source": "Met Office HadISST1",
        "url": HADISST_FULL_URL,
        "downloaded_utc": datetime.now(timezone.utc).isoformat(),
        "download_headers": response_headers,
        "compressed_sha256": _sha256(gz_path),
        "netcdf_sha256": _sha256(nc_path),
        **info,
    }
    metadata_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Saved NetCDF: {nc_path}")
    print(f"Latest month in official file: {info['latest_time']}")
    print(f"Saved metadata: {metadata_path}")
    return nc_path

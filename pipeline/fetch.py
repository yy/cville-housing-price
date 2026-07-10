"""Download all raw data sources into data/raw/ (skips files already present).

Run `python -m pipeline.fetch --force` to re-download everything.
"""

import json
import sys
import time
from pathlib import Path

import requests

from .config import (
    ALBEMARLE_FILES,
    CVILLE_PARCELS_LAYER,
    CVILLE_TABLES,
    PUMS_URL,
    RAW,
    TIGER_FILES,
    ZORI_URL,
)

UA = {"User-Agent": "cville-housing-price/0.1 (open data research)"}


def get_with_retry(url: str, params: dict, tries: int = 5) -> dict:
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=180)
            r.raise_for_status()
            return r.json()
        except (requests.Timeout, requests.ConnectionError):
            if attempt == tries - 1:
                raise
            wait = 10 * (attempt + 1)
            print(f"\n  timeout, retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def download(url: str, dest: Path, force: bool = False) -> Path:
    if dest.exists() and not force:
        print(f"  cached  {dest.name}")
        return dest
    print(f"  GET     {url}")
    with requests.get(url, headers=UA, stream=True, timeout=300) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        tmp.rename(dest)
    print(f"  saved   {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def fetch_arcgis_table(url: str, dest: Path, force: bool = False) -> Path:
    """Page through an ArcGIS REST table and save all rows as a JSON list."""
    if dest.exists() and not force:
        print(f"  cached  {dest.name}")
        return dest
    rows, offset = [], 0
    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": 2000,
        }
        data = get_with_retry(f"{url}/query", params)
        if "error" in data:
            raise RuntimeError(f"ArcGIS error for {url}: {data['error']}")
        feats = data.get("features", [])
        rows.extend(f["attributes"] for f in feats)
        print(f"  {dest.stem}: {len(rows)} rows", end="\r")
        if not data.get("exceededTransferLimit") or not feats:
            break
        offset += len(feats)
        time.sleep(0.2)
    dest.write_text(json.dumps(rows))
    print(f"  saved   {dest.name} ({len(rows)} rows)")
    return dest


def fetch_arcgis_geojson(url: str, dest: Path, force: bool = False) -> Path:
    """Page through an ArcGIS REST layer, saving features as GeoJSON (WGS84)."""
    if dest.exists() and not force:
        print(f"  cached  {dest.name}")
        return dest
    features, offset = [], 0
    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "outSR": 4326,
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": 1000,
        }
        data = get_with_retry(f"{url}/query", params)
        if "error" in data:
            raise RuntimeError(f"ArcGIS error for {url}: {data['error']}")
        feats = data.get("features", [])
        features.extend(feats)
        print(f"  {dest.stem}: {len(features)} features", end="\r")
        if len(feats) < 1000:
            break
        offset += len(feats)
        time.sleep(0.2)
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    print(f"  saved   {dest.name} ({len(features)} features)")
    return dest


def main() -> None:
    force = "--force" in sys.argv
    RAW.mkdir(parents=True, exist_ok=True)

    print("Charlottesville ArcGIS tables:")
    for name, url in CVILLE_TABLES.items():
        fetch_arcgis_table(url, RAW / f"{name}.json", force)
    fetch_arcgis_geojson(CVILLE_PARCELS_LAYER, RAW / "cville_parcels.geojson", force)

    print("Albemarle County files:")
    for name, url in ALBEMARLE_FILES.items():
        download(url, RAW / f"{name}.zip", force)

    print("Census boundaries:")
    for name, url in TIGER_FILES.items():
        download(url, RAW / f"{name}.zip", force)

    print("Zillow ZORI:")
    download(ZORI_URL, RAW / "zori_zip.csv", force)

    print("ACS PUMS (VA housing, 5-year):")
    download(PUMS_URL, RAW / "pums_hva.zip", force)

    print("done.")


if __name__ == "__main__":
    main()

"""Download raw data sources into data/raw/ (skips files already present).

Run `python -m pipeline.fetch --force` to re-download everything, or select one
or more source groups with `--group`.
"""

import argparse
import json
import time
from pathlib import Path

import requests

from .config import (
    ACS_RENT_TABLES,
    ACS_TABLE_URL,
    ALBEMARLE_FILES,
    CITY_FIPS,
    COUNTY_FIPS,
    CVILLE_PARCELS_LAYER,
    CVILLE_TABLES,
    PUMS_URL,
    RAW,
    STATE_FIPS,
    TIGER_FILES,
    ZORI_URL,
)

UA = {"User-Agent": "cville-housing-price/0.1 (open data research)"}
GROUPS = ("cville", "albemarle", "census", "zori", "pums", "acs")


def get_with_retry(url: str, params: dict, tries: int = 5) -> dict:
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=180)
            r.raise_for_status()
            return r.json()
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if attempt == tries - 1 or (status and status < 500):
                raise
            wait = 15 * (attempt + 1)
            print(f"\n  {type(e).__name__} ({status}), retrying in {wait}s")
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
    """Page through an ArcGIS REST table and save all rows as a JSON list.

    Pages on the table's object-id field (`where OID > last`) because this
    server rejects resultOffset beyond maxRecordCount.
    """
    if dest.exists() and not force:
        print(f"  cached  {dest.name}")
        return dest
    meta = get_with_retry(url, {"f": "json"})
    oid = meta.get("objectIdField") or next(
        f["name"] for f in meta["fields"] if f["type"] == "esriFieldTypeOID"
    )
    rows, last = [], None
    while True:
        params = {
            "where": "1=1" if last is None else f"{oid} > {last}",
            "outFields": "*",
            "orderByFields": oid,
            "f": "json",
            "resultRecordCount": 2000,
        }
        data = get_with_retry(f"{url}/query", params)
        if "error" in data:
            raise RuntimeError(f"ArcGIS error for {url}: {data['error']}")
        feats = data.get("features", [])
        if not feats:
            break
        rows.extend(f["attributes"] for f in feats)
        last = feats[-1]["attributes"][oid]
        print(f"  {dest.stem}: {len(rows)} rows", end="\r")
        if not data.get("exceededTransferLimit") and len(feats) < 2000:
            break
        time.sleep(0.2)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_text(json.dumps(rows))
    tmp.replace(dest)
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
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    tmp.replace(dest)
    print(f"  saved   {dest.name} ({len(features)} features)")
    return dest


def fetch_acs_table(table: str, dest: Path, force: bool = False) -> Path:
    """Stream a national ACS table and retain only local block groups."""
    if dest.exists() and not force:
        print(f"  cached  {dest.name}")
        return dest
    prefixes = [f"1500000US{STATE_FIPS}{county}" for county in (CITY_FIPS, COUNTY_FIPS)]
    url = ACS_TABLE_URL.format(table=table)
    print(f"  GET     {url}")
    with requests.get(url, headers=UA, stream=True, timeout=600) as r:
        r.raise_for_status()
        rows = []
        header = None
        buf = ""
        for chunk in r.iter_content(chunk_size=1 << 20):
            buf += chunk.decode("utf-8", errors="replace")
            lines = buf.split("\n")
            buf = lines.pop()
            for line in lines:
                if header is None:
                    header = line
                elif line.startswith(tuple(prefixes)):
                    rows.append(line)
        if buf and buf.startswith(tuple(prefixes)):
            rows.append(buf)
    if header is None:
        raise RuntimeError(f"empty ACS response for {table}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_text(header + "\n" + "\n".join(rows) + "\n")
    tmp.replace(dest)
    print(f"  saved   {dest.name} ({len(rows)} rows)")
    return dest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--group",
        action="append",
        choices=GROUPS,
        help="fetch only this source group; may be repeated (default: all)",
    )
    parser.add_argument("--force", action="store_true", help="replace cached files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected = set(args.group or GROUPS)
    force = args.force
    RAW.mkdir(parents=True, exist_ok=True)

    if "cville" in selected:
        print("Charlottesville ArcGIS tables:")
        for name, url in CVILLE_TABLES.items():
            fetch_arcgis_table(url, RAW / f"{name}.json", force)
        fetch_arcgis_geojson(
            CVILLE_PARCELS_LAYER, RAW / "cville_parcels.geojson", force
        )

    if "albemarle" in selected:
        print("Albemarle County files:")
        for name, url in ALBEMARLE_FILES.items():
            download(url, RAW / f"{name}.zip", force)

    if "census" in selected:
        print("Census boundaries:")
        for name, url in TIGER_FILES.items():
            download(url, RAW / f"{name}.zip", force)

    if "zori" in selected:
        print("Zillow ZORI:")
        download(ZORI_URL, RAW / "zori_zip.csv", force)

    if "pums" in selected:
        print("ACS PUMS (VA housing, 5-year):")
        download(PUMS_URL, RAW / "pums_hva.zip", force)

    if "acs" in selected:
        print("ACS block-group tables:")
        for table in ACS_RENT_TABLES:
            fetch_acs_table(table, RAW / f"acs_{table}_bg.csv", force)

    print("done.")


if __name__ == "__main__":
    main()

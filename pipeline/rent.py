"""Rent layers.

1. ACS block-group median gross rent (keyless Census table-based summary files)
2. A characteristics-adjusted *rent factor*: observed ACS rent divided by the
   rent predicted from the block group's renter housing stock, using a rent
   hedonic fit on ACS PUMS microdata for the local PUMA(s).
3. Zillow ZORI by ZIP (latest level + 12-month change) on ZCTA polygons.

Outputs: data/processed/rent_bg.parquet, site/data/zori.geojson
"""

import io
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import (
    CITY_FIPS,
    COUNTY_FIPS,
    PROCESSED,
    RAW,
    SITE_DATA,
    STATE_FIPS,
    acs_table_path,
)


def acs_table(table: str) -> pd.DataFrame:
    """Read a fetched ACS table containing the local block groups."""
    cache = acs_table_path(table)
    if not cache.exists():
        raise FileNotFoundError(f"missing tracked ACS snapshot {cache}")
    df = pd.read_csv(cache, sep="|", dtype={"GEO_ID": str})
    num = df.select_dtypes("number").columns
    df[num] = df[num].where(df[num] > -6666)  # ACS suppression sentinels
    df["bg_geoid"] = df["GEO_ID"].str[9:]
    return df


def load_acs() -> pd.DataFrame:
    rent = acs_table("b25064")[["bg_geoid", "B25064_E001", "B25064_M001"]]
    rent.columns = ["bg_geoid", "acs_rent", "acs_rent_moe"]

    ten = acs_table("b25003")[["bg_geoid", "B25003_E003"]]
    ten.columns = ["bg_geoid", "renters"]

    # renter bedrooms: B25042_E010..E015 = renter 0..5+ bedrooms
    bed = acs_table("b25042")
    counts = bed[[f"B25042_E{i:03d}" for i in range(10, 16)]]
    nbeds = np.array([0, 1, 2, 3, 4, 5])
    tot = counts.sum(axis=1)
    bed_out = pd.DataFrame(
        {
            "bg_geoid": bed["bg_geoid"],
            "mean_beds": (counts * nbeds).sum(axis=1) / tot.replace(0, np.nan),
        }
    )

    # renter units in structure: B25032_E014/E015 = renter 1-detached/attached
    uni = acs_table("b25032")
    renter_tot = uni["B25032_E013"].replace(0, np.nan)
    sf_out = pd.DataFrame(
        {
            "bg_geoid": uni["bg_geoid"],
            "share_sf": (uni["B25032_E014"] + uni["B25032_E015"]) / renter_tot,
        }
    )

    yb = acs_table("b25037")[["bg_geoid", "B25037_E003"]]
    yb.columns = ["bg_geoid", "renter_yrblt"]

    out = rent.merge(ten, on="bg_geoid", how="left")
    for extra in (bed_out, sf_out, yb):
        out = out.merge(extra, on="bg_geoid", how="left")
    for c in out.columns[1:]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def local_pumas() -> set[str]:
    puma = gpd.read_file(f"zip://{RAW / 'tiger_puma.zip'}").to_crs(4326)
    bg = gpd.read_file(f"zip://{RAW / 'tiger_bg.zip'}")
    area = bg[
        (bg["STATEFP"] == STATE_FIPS) & (bg["COUNTYFP"].isin([CITY_FIPS, COUNTY_FIPS]))
    ].to_crs(4326)
    region = area.union_all()
    hits = puma[puma.intersects(region)].copy()
    frac = hits.geometry.intersection(region).area / hits.geometry.area
    codes = set(hits.loc[frac > 0.10, "PUMACE20"])
    print(f"  local 2020 PUMAs: {sorted(codes)}")
    return codes


def pums_hedonic() -> dict:
    """Fit log(gross rent) ~ bedrooms + single-family + year built on local
    PUMS renters (2022+ samples, which carry 2020 PUMA codes)."""
    pumas = local_pumas()
    cols = ["SERIALNO", "PUMA", "WGTP", "ADJHSG", "GRNTP", "BDSP", "BLD", "YRBLT"]
    with zipfile.ZipFile(RAW / "pums_hva.zip") as z, z.open("psam_h51.csv") as f:
        df = pd.read_csv(
            io.TextIOWrapper(f, encoding="utf-8"),
            usecols=cols,
            dtype={"SERIALNO": str, "PUMA": str},
        )
    df["year"] = df["SERIALNO"].str[:4].astype(int)
    df = df[(df["year"] >= 2022) & df["PUMA"].isin(pumas)]
    df = df[(df["GRNTP"] > 0) & df["BDSP"].notna() & df["YRBLT"].notna()]

    df["log_rent"] = np.log(df["GRNTP"] * df["ADJHSG"] / 1_000_000)
    df["beds"] = df["BDSP"].clip(0, 4)
    df["sf"] = df["BLD"].isin([2, 3]).astype(float)
    df["yrblt"] = df["YRBLT"].clip(1939, 2023)

    X = np.column_stack(
        [np.ones(len(df)), df["beds"], df["sf"], (df["yrblt"] - 2000) / 10]
    )
    w = df["WGTP"].to_numpy(dtype=float)
    y = df["log_rent"].to_numpy()
    beta, *_ = np.linalg.lstsq(X * np.sqrt(w)[:, None], y * np.sqrt(w), rcond=None)
    resid = y - X @ beta
    r2 = 1 - np.average(resid**2, weights=w) / np.average(
        (y - np.average(y, weights=w)) ** 2, weights=w
    )
    print(
        f"  PUMS hedonic: n={len(df)}, R²={r2:.2f}, "
        f"beta(const,beds,sf,yrblt/decade)={np.round(beta, 3)}"
    )
    return {"const": beta[0], "beds": beta[1], "sf": beta[2], "yrblt": beta[3]}


def rent_factors(acs: pd.DataFrame, beta: dict) -> pd.DataFrame:
    df = acs.copy()
    pred_log = (
        beta["const"]
        + beta["beds"] * df["mean_beds"]
        + beta["sf"] * df["share_sf"].fillna(0)
        + beta["yrblt"] * (df["renter_yrblt"].clip(1939, 2023) - 2000) / 10
    )
    df["pred_rent"] = np.exp(pred_log)
    df["rent_factor"] = df["acs_rent"] / df["pred_rent"]
    # normalize to renter-weighted mean 1.0
    ok = df["rent_factor"].notna() & df["renters"].gt(0)
    mean = np.average(df.loc[ok, "rent_factor"], weights=df.loc[ok, "renters"])
    df["rent_factor"] /= mean
    df["pred_rent"] *= mean
    # suppress unreliable estimates (tiny renter stock or huge MOE)
    bad = (df["renters"] < 30) | (df["acs_rent_moe"] / df["acs_rent"] > 0.5)
    df.loc[bad, ["rent_factor"]] = np.nan
    return df


def zori_layer() -> None:
    z = pd.read_csv(RAW / "zori_zip.csv", dtype={"RegionName": str})
    z = z[
        (z["State"] == "VA")
        & z["CountyName"].isin(["Charlottesville City", "Albemarle County"])
    ]
    months = [c for c in z.columns if c[:2] == "20"]
    latest, yearago = months[-1], months[-13]
    z = z[["RegionName", latest, yearago]].rename(columns={"RegionName": "zip"})
    z["zori"] = z[latest].round(0)
    z["zori_yoy"] = ((z[latest] / z[yearago] - 1) * 100).round(1)

    zcta = gpd.read_file(f"zip://{RAW / 'tiger_zcta.zip'}")
    zcta = zcta[zcta["ZCTA5CE20"].isin(z["zip"])][["ZCTA5CE20", "geometry"]]
    out = zcta.merge(
        z[["zip", "zori", "zori_yoy"]], left_on="ZCTA5CE20", right_on="zip"
    )
    out["geometry"] = out["geometry"].simplify(0.0005, preserve_topology=True)
    out[["zip", "zori", "zori_yoy", "geometry"]].to_file(
        SITE_DATA / "zori.geojson", driver="GeoJSON"
    )
    print(f"  ZORI: {len(out)} ZIPs, latest month {latest}")


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    print("ACS block-group tables:")
    acs = load_acs()
    beta = pums_hedonic()
    df = rent_factors(acs, beta)
    df.to_parquet(PROCESSED / "rent_bg.parquet", index=False)
    ok = df["rent_factor"].notna()
    print(
        f"rent factors for {ok.sum()} of {len(df)} BGs; "
        f"range {df['rent_factor'].min():.2f}–{df['rent_factor'].max():.2f}"
    )
    zori_layer()


if __name__ == "__main__":
    main()

"""Assign each sold parcel to a census block group.

Output: data/processed/sales_geo.parquet = sales.parquet + lon/lat + GEOID.
"""

import geopandas as gpd
import pandas as pd

from .config import CITY_FIPS, COUNTY_FIPS, PROCESSED, RAW, STATE_FIPS


def norm_gpin(s: pd.Series) -> pd.Series:
    return (
        s.astype(str).str.replace(r"\.0$", "", regex=True).str.strip().str.lstrip("0")
    )


def parcel_points() -> gpd.GeoDataFrame:
    cv = gpd.read_file(RAW / "cville_parcels.geojson")[["GPIN", "geometry"]]
    cv["locality"] = "cville"
    al = gpd.read_file(f"zip://{RAW / 'alb_parcels_shape.zip'}!Parcels_current.shp")
    al = al.to_crs(4326)[["GPIN", "geometry"]]
    al["locality"] = "albemarle"
    parcels = pd.concat([cv, al], ignore_index=True)
    parcels["gpin"] = norm_gpin(parcels["GPIN"])
    parcels = parcels.dropna(subset=["geometry"]).drop_duplicates(["locality", "gpin"])
    parcels["geometry"] = parcels["geometry"].representative_point()
    return gpd.GeoDataFrame(parcels[["locality", "gpin", "geometry"]], crs=4326)


def block_groups() -> gpd.GeoDataFrame:
    bg = gpd.read_file(f"zip://{RAW / 'tiger_bg.zip'}")
    bg = bg[
        (bg["STATEFP"] == STATE_FIPS) & (bg["COUNTYFP"].isin([CITY_FIPS, COUNTY_FIPS]))
    ]
    return bg[["GEOID", "geometry"]].to_crs(4326)


def main() -> None:
    sales = pd.read_parquet(PROCESSED / "sales.parquet")
    sales["gpin"] = norm_gpin(sales["gpin"])

    pts = parcel_points()
    bg = block_groups()
    pts = gpd.sjoin(pts, bg, how="left", predicate="within").drop(columns="index_right")
    pts["lon"] = pts.geometry.x
    pts["lat"] = pts.geometry.y
    geo = pd.DataFrame(pts[["locality", "gpin", "GEOID", "lon", "lat"]])
    geo = geo.rename(columns={"GEOID": "bg_geoid"})
    geo["tract_geoid"] = geo["bg_geoid"].str[:11]

    out = sales.merge(geo, on=["locality", "gpin"], how="left")
    matched = out["bg_geoid"].notna().mean()
    out.to_parquet(PROCESSED / "sales_geo.parquet", index=False)
    print(f"{len(out)} sales, {matched:.1%} matched to a block group")
    print(out.groupby("locality")["bg_geoid"].nunique())


if __name__ == "__main__":
    main()

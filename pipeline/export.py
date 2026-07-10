"""Bake site/data/: factor choropleth GeoJSON + metadata.

Every block group is rendered; a BG whose factor was pooled up to its tract
(or locality) carries the pooled estimate and a `pooled` flag.
"""

import json

import geopandas as gpd
import pandas as pd

from .config import CITY_FIPS, COUNTY_FIPS, PROCESSED, RAW, SITE_DATA, STATE_FIPS


def load_bg() -> gpd.GeoDataFrame:
    bg = gpd.read_file(f"zip://{RAW / 'tiger_bg.zip'}")
    bg = bg[
        (bg["STATEFP"] == STATE_FIPS) & (bg["COUNTYFP"].isin([CITY_FIPS, COUNTY_FIPS]))
    ].to_crs(4326)
    bg["locality"] = bg["COUNTYFP"].map({CITY_FIPS: "cville", COUNTY_FIPS: "albemarle"})
    return bg[["GEOID", "locality", "geometry"]]


def main() -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    factors = pd.read_parquet(PROCESSED / "factors.parquet")
    sales = pd.read_parquet(PROCESSED / "sales_geo.parquet")
    bg = load_bg()

    # map each BG to its area unit (BG itself, pooled tract, or locality)
    lookup = {}
    for _, r in factors.iterrows():
        lookup[r["area"]] = r
    rows = []
    for _, g in bg.iterrows():
        geoid, loc = g["GEOID"], g["locality"]
        for key, pooled in (
            (geoid, False),
            ("T" + geoid[:11], True),
            ("L" + loc, True),
        ):
            if key in lookup:
                r = lookup[key]
                rows.append(
                    {
                        "GEOID": geoid,
                        "locality": loc,
                        "factor": round(float(r["factor"]), 3),
                        "factor_lo": round(float(r["factor_lo"]), 3),
                        "factor_hi": round(float(r["factor_hi"]), 3),
                        "n_sales": int(r["n_sales"]),
                        "median_price": int(r["median_price"]),
                        "median_ppsf": int(r["median_ppsf"]),
                        "median_sqft": int(r["median_sqft"]),
                        "pooled": pooled,
                        "unit": key,
                    }
                )
                break
        else:
            rows.append({"GEOID": geoid, "locality": loc, "factor": None})

    out = bg.merge(pd.DataFrame(rows), on="GEOID", suffixes=("", "_x"))
    out["geometry"] = out["geometry"].simplify(0.0002, preserve_topology=True)
    out = out.drop(columns=[c for c in out.columns if c.endswith("_x")])
    out.to_file(SITE_DATA / "factors.geojson", driver="GeoJSON")

    # city/county boundary for emphasis (dissolved by locality)
    boundary = load_bg().dissolve("locality").reset_index()
    boundary["geometry"] = boundary["geometry"].simplify(0.0002, preserve_topology=True)
    boundary[["locality", "geometry"]].to_file(
        SITE_DATA / "localities.geojson", driver="GeoJSON"
    )

    stats = json.loads((PROCESSED / "model_stats.json").read_text())
    stats["built"] = pd.Timestamp.now().strftime("%Y-%m-%d")
    stats["localities"] = {
        loc: {
            "n_sales": int(n),
            "median_price": int(m),
        }
        for loc, n, m in sales.dropna(subset=["bg_geoid"])
        .groupby("locality")
        .agg(n=("sale_price", "size"), m=("sale_price", "median"))
        .itertuples()
    }
    (SITE_DATA / "meta.json").write_text(json.dumps(stats, indent=1))
    print(f"wrote {len(out)} block groups; meta: {stats}")


if __name__ == "__main__":
    main()

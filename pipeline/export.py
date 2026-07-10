"""Bake site/data/: factor choropleth GeoJSON + metadata.

Every block group is rendered; a BG whose factor was pooled up to its tract
(or locality) carries the pooled estimate and a `pooled` flag.
"""

import json

import geopandas as gpd
import pandas as pd

from .config import (
    CITY_FIPS,
    COUNTY_FIPS,
    DOWN_PAYMENT,
    MORTGAGE_RATE,
    PROCESSED,
    RAW,
    SITE_DATA,
    STATE_FIPS,
    TERM_YEARS,
)


def monthly_payment(price: float) -> float:
    """Monthly principal + interest on a standard mortgage."""
    loan = price * (1 - DOWN_PAYMENT)
    r = MORTGAGE_RATE / 12
    n = TERM_YEARS * 12
    return loan * r / (1 - (1 + r) ** -n)


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

    def area_row(geoid: str, loc: str):
        for key, pooled in (
            (geoid, False),
            ("T" + geoid[:11], True),
            ("L" + loc, True),
        ):
            if key in lookup:
                return lookup[key], key, pooled
        return None, None, None

    # reference price: metro-average cost of the typical recently-sold home
    # (each recent sale deflated by its area's factor, then take the median)
    recent = sales.dropna(subset=["bg_geoid"]).copy()
    recent = recent[
        recent["sale_date"] >= recent["sale_date"].max() - pd.Timedelta(days=365)
    ]
    recent["factor"] = [
        float(r["factor"]) if r is not None else None
        for r, _, _ in (
            area_row(g, loc) for g, loc in zip(recent["bg_geoid"], recent["locality"])
        )
    ]
    recent = recent.dropna(subset=["factor"])
    ref_price = float((recent["sale_price"] / recent["factor"]).median())

    base_monthly = monthly_payment(ref_price)
    rows = []
    for _, g in bg.iterrows():
        geoid, loc = g["GEOID"], g["locality"]
        r, key, pooled = area_row(geoid, loc)
        if r is None:
            rows.append({"GEOID": geoid, "locality": loc, "factor": None})
            continue
        factor = float(r["factor"])
        est_price = ref_price * factor
        mo_pay = monthly_payment(est_price)
        rows.append(
            {
                "GEOID": geoid,
                "locality": loc,
                "factor": round(factor, 3),
                "factor_lo": round(float(r["factor_lo"]), 3),
                "factor_hi": round(float(r["factor_hi"]), 3),
                "n_sales": int(r["n_sales"]),
                "median_price": int(r["median_price"]),
                "median_ppsf": int(r["median_ppsf"]),
                "median_sqft": int(r["median_sqft"]),
                "est_price": int(round(est_price, -3)),
                "mo_pay": int(round(mo_pay, -1)),
                "mo_delta": int(round(mo_pay - base_monthly, -1)),
                "pooled": pooled,
                "unit": key,
            }
        )

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
    stats["ref_price"] = int(round(ref_price, -3))
    stats["base_monthly"] = int(round(base_monthly, -1))
    stats["mortgage"] = {
        "rate": MORTGAGE_RATE,
        "down": DOWN_PAYMENT,
        "term_years": TERM_YEARS,
    }
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

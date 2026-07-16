"""Bake site/data/: factor choropleth GeoJSON + metadata.

Every block group is rendered; a BG whose factor was pooled up to its tract
(or locality) carries the pooled estimate and a `pooled` flag.
"""

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .config import (
    BIKE_RANGE_MI,
    CITY_FIPS,
    COMMUTE_DAYS_PER_MONTH,
    COST_PER_MILE,
    COUNTY_FIPS,
    DOWN_PAYMENT,
    DOWNTOWN,
    EBIKE_RANGE_MI,
    MORTGAGE_RATE,
    PROCESSED,
    RAW,
    SALES_START,
    SITE_DATA,
    STATE_FIPS,
    TERM_YEARS,
    UVA,
)

UTM = 32617  # UTM 17N, meters


def bg_distances(sales: pd.DataFrame) -> dict[str, float]:
    """Straight-line miles from each BG's sales-weighted centroid to the
    nearer of downtown / UVA."""
    cent = (
        sales.dropna(subset=["bg_geoid", "lon", "lat"])
        .groupby("bg_geoid")[["lon", "lat"]]
        .mean()
        .reset_index()
    )
    pts = gpd.GeoDataFrame(
        cent, geometry=gpd.points_from_xy(cent["lon"], cent["lat"]), crs=4326
    ).to_crs(UTM)
    anchors = gpd.GeoSeries(
        [shapely.Point(DOWNTOWN), shapely.Point(UVA)], crs=4326
    ).to_crs(UTM)
    meters = pd.concat([pts.geometry.distance(a) for a in anchors], axis=1).min(axis=1)
    return dict(zip(cent["bg_geoid"], meters * 0.000621371))


def driving_cost(dist_mi: float) -> float:
    """Monthly cost of commuting that distance by car (round trips)."""
    return dist_mi * 2 * COMMUTE_DAYS_PER_MONTH * COST_PER_MILE


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
    # the cleaned data reaches back further for the era models; everything on
    # this page describes the headline window only
    sales = sales[sales["sale_date"] >= SALES_START]
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
    dist = bg_distances(sales)

    rows = []
    for _, g in bg.iterrows():
        geoid, loc = g["GEOID"], g["locality"]
        r, key, pooled = area_row(geoid, loc)
        if r is None or geoid not in dist:
            rows.append(
                {
                    "GEOID": geoid,
                    "locality": loc,
                    "factor": None,
                    "in_zone": int(loc == "cville"),
                    "pooled": 0,
                }
            )
            continue
        factor = float(r["factor"])
        est_price = ref_price * factor
        mo_pay = monthly_payment(est_price)
        dist_mi = dist[geoid]
        drive_mo = driving_cost(dist_mi)
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
                "dist_mi": round(dist_mi, 1),
                "drive_mo": int(round(drive_mo, -1)),
                "allin_mo": int(round(mo_pay + drive_mo, -1)),
                "allin2_mo": int(round(mo_pay + 2 * drive_mo, -1)),
                # ints, not Python bools: the OGR GeoJSON driver would write
                # bools as the strings "True"/"False"
                "in_zone": int(loc == "cville"),  # bikeable = city proper
                "pooled": int(pooled),
                "unit": key,
            }
        )

    rows_df = pd.DataFrame(rows)
    rent = pd.read_parquet(PROCESSED / "rent_bg.parquet")
    rent = rent[["bg_geoid", "acs_rent", "rent_factor", "pred_rent", "renters"]]
    rent["rent_factor"] = rent["rent_factor"].round(3)
    rent["pred_rent"] = rent["pred_rent"].round(0)
    rows_df = rows_df.merge(
        rent, left_on="GEOID", right_on="bg_geoid", how="left"
    ).drop(columns="bg_geoid")

    out = bg.merge(rows_df, on="GEOID", suffixes=("", "_x"))
    out["geometry"] = out["geometry"].simplify(0.0002, preserve_topology=True)
    out = out.drop(columns=[c for c in out.columns if c.endswith("_x")])
    out.to_file(SITE_DATA / "factors.geojson", driver="GeoJSON")

    # city/county boundary for emphasis (dissolved by locality)
    boundary = load_bg().dissolve("locality").reset_index()
    boundary["geometry"] = boundary["geometry"].simplify(0.0002, preserve_topology=True)
    boundary[["locality", "geometry"]].to_file(
        SITE_DATA / "localities.geojson", driver="GeoJSON"
    )

    # cost-of-distance chart data: per-BG dots + sales-weighted LOESS curves
    df = pd.DataFrame(rows).dropna(subset=["factor"])

    def loess(xcol, ycol, grid, h=4.0):
        """Tricube-weighted local linear regression, weighted by n_sales."""
        x = df[xcol].to_numpy(float)
        y = df[ycol].to_numpy(float)
        w0 = df["n_sales"].to_numpy(float)
        out = []
        for x0 in grid:
            d = np.abs(x - x0) / h
            w = np.where(d < 1, (1 - d**3) ** 3, 0) * w0
            if w.sum() < 30:
                out.append(None)
                continue
            X = np.column_stack([np.ones_like(x), x - x0])
            beta = np.linalg.lstsq(X * w[:, None] ** 0.5, y * w**0.5, rcond=None)[0]
            out.append(round(float(beta[0])))
        return out

    grid = np.arange(0.5, min(df["dist_mi"].max(), 20) + 0.01, 0.5)
    curves = {
        "mi": [round(g, 1) for g in grid],
        "housing": loess("dist_mi", "mo_pay", grid),
        "allin": loess("dist_mi", "allin_mo", grid),
        "allin2": loess("dist_mi", "allin2_mo", grid),
    }
    insight = {
        "bike_range_mi": BIKE_RANGE_MI,
        "ebike_range_mi": EBIKE_RANGE_MI,
        "curves": curves,
        "bgs": df[
            ["GEOID", "locality", "dist_mi", "mo_pay", "allin_mo", "n_sales", "in_zone"]
        ].to_dict("records"),
    }
    (SITE_DATA / "insight.json").write_text(json.dumps(insight))

    stats = json.loads((PROCESSED / "model_stats.json").read_text())
    stats["built"] = pd.Timestamp.now().strftime("%Y-%m-%d")
    stats["ref_price"] = int(round(ref_price, -3))
    stats["base_monthly"] = int(round(base_monthly, -1))
    stats["mortgage"] = {
        "rate": MORTGAGE_RATE,
        "down": DOWN_PAYMENT,
        "term_years": TERM_YEARS,
    }
    stats["commute"] = {
        "cost_per_mile": COST_PER_MILE,
        "days_per_month": COMMUTE_DAYS_PER_MONTH,
        "bike_range_mi": BIKE_RANGE_MI,
        "ebike_range_mi": EBIKE_RANGE_MI,
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

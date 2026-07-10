"""Fine-grained smoothed location-value surface.

Gaussian-kernel smoothing of per-sale location components (area effect +
residual from the hedonic model) on a square grid. Cells too far from any
sale (low effective sample) are suppressed rather than extrapolated.

Output: site/data/surface.geojson with `factor_fine` per cell.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .config import (
    CITY_FIPS,
    COUNTY_FIPS,
    PROCESSED,
    RAW,
    SITE_DATA,
    STATE_FIPS,
    SURFACE_BW_M,
    SURFACE_CELL_M,
    SURFACE_MIN_N,
)

UTM = 32617


def main() -> None:
    sales = pd.read_parquet(PROCESSED / "sale_loc.parquet").dropna()
    pts = gpd.GeoDataFrame(
        sales,
        geometry=gpd.points_from_xy(sales["lon"], sales["lat"]),
        crs=4326,
    ).to_crs(UTM)
    sx = pts.geometry.x.to_numpy()
    sy = pts.geometry.y.to_numpy()
    loc = pts["loc"].to_numpy()

    bg = gpd.read_file(f"zip://{RAW / 'tiger_bg.zip'}")
    region = (
        bg[
            (bg["STATEFP"] == STATE_FIPS)
            & (bg["COUNTYFP"].isin([CITY_FIPS, COUNTY_FIPS]))
        ]
        .to_crs(UTM)
        .union_all()
    )

    minx, miny, maxx, maxy = region.bounds
    c = SURFACE_CELL_M
    xs = np.arange(minx, maxx, c)
    ys = np.arange(miny, maxy, c)
    gx, gy = np.meshgrid(xs + c / 2, ys + c / 2)
    gx, gy = gx.ravel(), gy.ravel()

    # keep only cells inside the region
    cells = gpd.GeoSeries(gpd.points_from_xy(gx, gy), crs=UTM)
    inside = cells.within(region).to_numpy()
    gx, gy = gx[inside], gy[inside]

    # gaussian kernel smoothing, chunked to bound memory
    bw2 = SURFACE_BW_M**2
    vals = np.full(len(gx), np.nan)
    ess = np.zeros(len(gx))
    for i in range(0, len(gx), 500):
        dx = gx[i : i + 500, None] - sx[None, :]
        dy = gy[i : i + 500, None] - sy[None, :]
        w = np.exp(-(dx * dx + dy * dy) / (2 * bw2))
        sw = w.sum(axis=1)
        ess[i : i + 500] = sw
        with np.errstate(invalid="ignore"):
            vals[i : i + 500] = (w @ loc) / sw

    keep = ess >= SURFACE_MIN_N
    gx, gy, vals = gx[keep], gy[keep], vals[keep]

    # normalize like the block-group factors: sales-weighted mean -> 1.0
    mean_loc = loc.mean()
    factor = np.exp(vals - mean_loc)

    half = c / 2
    boxes = [
        shapely.box(x - half, y - half, x + half, y + half) for x, y in zip(gx, gy)
    ]
    out = gpd.GeoDataFrame(
        {"factor_fine": np.round(factor, 3)}, geometry=boxes, crs=UTM
    ).to_crs(4326)
    out["geometry"] = out["geometry"].apply(lambda g: shapely.set_precision(g, 0.0001))
    out.to_file(SITE_DATA / "surface.geojson", driver="GeoJSON")
    print(
        f"surface: {len(out)} cells of {len(inside)} "
        f"(bw {SURFACE_BW_M} m, cell {SURFACE_CELL_M} m), "
        f"factor range {factor.min():.2f}-{factor.max():.2f}"
    )


if __name__ == "__main__":
    main()

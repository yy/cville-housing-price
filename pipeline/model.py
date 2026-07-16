"""Fit the hedonic price model and extract block-group price factors.

log(price) ~ house attributes + year-quarter FE + area effect,
where the area effect is a block-group dummy (pooled up to tract when a
block group has too few sales). The exported price factor is
exp(area effect - sales-weighted mean effect), i.e. normalized so the
sales-weighted GEOMETRIC mean factor is 1.0 ("typical location" = 1.00).

Outputs:
  data/processed/factors.parquet  (one row per area unit)
  data/processed/diagnostics.md
"""

import json

import numpy as np
import pandas as pd
import pyfixest as pf

from .config import MIN_SALES_PER_BG, PROCESSED, SALES_START


def prepare(start: str = SALES_START, end: str | None = None) -> pd.DataFrame:
    """Load geocoded sales, filter to a modeling window, build features."""
    df = pd.read_parquet(PROCESSED / "sales_geo.parquet")
    df = df[df["sale_date"] >= start]
    if end is not None:
        df = df[df["sale_date"] <= end]
    return build_features(df)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    n0 = len(df)
    df = df.dropna(subset=["bg_geoid", "sqft", "sale_price", "year_built"]).copy()
    df = df[df["sqft"] > 0]

    df["log_price"] = np.log(df["sale_price"])
    df["log_sqft"] = np.log(df["sqft"])
    df["beds"] = df["beds"].fillna(0).clip(0, 8)
    df["baths"] = df["baths"].fillna(1).clip(0.5, 8)
    year = df["sale_date"].dt.year
    df["age"] = (year - df["year_built"]).clip(0, 250)
    df["age2"] = df["age"] ** 2 / 100
    df["log_acre"] = np.log1p(df["acreage"].fillna(0).clip(0, 500))
    df["stories"] = df["stories"].fillna(1).clip(0.5, 4)
    df["yq"] = year.astype(str) + "Q" + df["sale_date"].dt.quarter.astype(str)

    # lump rare grade levels so dummies stay estimable
    counts = df["grade"].value_counts()
    rare = counts[counts < 50].index
    df.loc[df["grade"].isin(rare), "grade"] = df["locality"].map(
        {"cville": "cv_other", "albemarle": "al_other"}
    )

    # area unit: block group, pooled to tract when thin
    bg_n = df.groupby("bg_geoid")["bg_geoid"].transform("size")
    df["area"] = np.where(
        bg_n >= MIN_SALES_PER_BG, df["bg_geoid"], "T" + df["tract_geoid"]
    )
    # a pooled tract can itself be thin; then fall back to locality
    area_n = df.groupby("area")["area"].transform("size")
    df["area"] = np.where(area_n >= MIN_SALES_PER_BG, df["area"], "L" + df["locality"])
    print(f"model sample {len(df)} of {n0}; {df['area'].nunique()} area units")
    return df


def fit(df: pd.DataFrame):
    fml = (
        "log_price ~ log_sqft + beds + baths + age + age2 + log_acre"
        " + stories + C(ptype) + C(grade) + C(area) | yq"
    )
    return pf.feols(fml, data=df, vcov={"CRV1": "area"})


def extract_factors(m, df: pd.DataFrame) -> pd.DataFrame:
    """Area effects re-centered on the sales-weighted mean, with delta-method
    CIs from the full CRV1 covariance of the area dummies.

    The reported quantity per area a is c_a = fe_a - Σ_b w_b·fe_b (w = sales
    shares). Its variance is g'Σg where g is the gradient of c_a over the
    estimated dummies (the dropped reference has fe = 0 with no uncertainty
    of its own, but its *centered* effect still inherits variance from the
    weighted mean — so no area gets a zero-width interval).
    """
    coefs = m.coef()
    prefix, suffix = "C(area)[T.", "]"
    dummy = {
        n[len(prefix) : -len(suffix)]: n
        for n in m._coefnames
        if n.startswith(prefix) and n.endswith(suffix)
    }
    area_set = set(df["area"].unique())
    unknown = set(dummy) - area_set
    if unknown:
        raise RuntimeError(f"model has area dummies not in the data: {sorted(unknown)}")
    missing = area_set - set(dummy)
    if len(missing) != 1:
        raise RuntimeError(
            "expected exactly one dropped reference area level, "
            f"got {len(missing)}: {sorted(missing)[:5]}"
        )
    ref = missing.pop()
    areas = sorted(area_set)
    est = [a for a in areas if a != ref]  # areas with an estimated dummy

    # sales-share weights over ALL areas (reference included)
    counts = df["area"].value_counts()
    w = np.array([counts[a] for a in areas], dtype=float)
    w /= w.sum()

    fe = np.array([0.0 if a == ref else float(coefs[dummy[a]]) for a in areas])
    mean_fe = float(w @ fe)

    # covariance of the estimated area dummies, aligned to `est`
    names = list(m._coefnames)
    cols = [names.index(dummy[a]) for a in est]
    vcov = np.asarray(m._vcov)[np.ix_(cols, cols)]
    w_est = np.array([w[areas.index(a)] for a in est])

    pos = {a: i for i, a in enumerate(est)}
    se_c = np.empty(len(areas))
    for i, a in enumerate(areas):
        g = -w_est.copy()
        if a != ref:
            g[pos[a]] += 1.0
        se_c[i] = np.sqrt(g @ vcov @ g)

    out = pd.DataFrame({"area": areas, "fe": fe, "se": se_c})
    out["n_sales"] = out["area"].map(counts)
    # normalize: sales-weighted mean effect = 0, i.e. the sales-weighted
    # geometric mean factor = 1.0 ("typical location")
    centered = fe - mean_fe
    out["factor"] = np.exp(centered)
    out["factor_lo"] = np.exp(centered - 1.96 * se_c)
    out["factor_hi"] = np.exp(centered + 1.96 * se_c)

    stats = (
        df.assign(ppsf=df["sale_price"] / df["sqft"])
        .groupby("area")
        .agg(
            median_price=("sale_price", "median"),
            median_ppsf=("ppsf", "median"),
            median_sqft=("sqft", "median"),
            locality=("locality", "first"),
        )
        .reset_index()
    )
    return out.merge(stats, on="area")


def diagnostics(m, df: pd.DataFrame, factors: pd.DataFrame) -> str:
    core = [
        "log_sqft",
        "beds",
        "baths",
        "age",
        "age2",
        "log_acre",
        "stories",
    ]
    coefs, ses = m.coef(), m.se()
    lines = [
        "# Hedonic model diagnostics",
        "",
        f"- N = {int(m._N)}, R² = {m._r2:.3f}",
        f"- Area units: {df['area'].nunique()} "
        f"(block groups pooled to tract/locality below {MIN_SALES_PER_BG} sales)",
        "",
        "| coef | est | se |",
        "|---|---|---|",
    ]
    for c in core:
        lines.append(f"| {c} | {coefs[c]:.4f} | {ses[c]:.4f} |")
    lines += [
        "",
        "## Factor distribution",
        "",
        str(factors["factor"].describe().round(3).to_dict()),
        "",
        "## Top / bottom areas",
        "",
        factors.nlargest(5, "factor")[
            ["area", "factor", "n_sales", "median_ppsf"]
        ].to_markdown(index=False),
        "",
        factors.nsmallest(5, "factor")[
            ["area", "factor", "n_sales", "median_ppsf"]
        ].to_markdown(index=False),
        "",
    ]
    return "\n".join(lines)


def dump_location_components(m, df: pd.DataFrame, factors: pd.DataFrame) -> None:
    """Per-sale location value (area effect + residual) for the smoothed
    fine-grained surface."""
    fe = dict(zip(factors["area"], factors["fe"]))
    out = df[["lon", "lat", "sale_date"]].copy()
    out["loc"] = df["area"].map(fe).astype(float) + m.resid()
    out.to_parquet(PROCESSED / "sale_loc.parquet", index=False)


def main() -> None:
    df = prepare()
    m = fit(df)
    factors = extract_factors(m, df)
    factors.to_parquet(PROCESSED / "factors.parquet", index=False)
    dump_location_components(m, df, factors)
    report = diagnostics(m, df, factors)
    (PROCESSED / "diagnostics.md").write_text(report)
    stats = {
        "n_sales": int(m._N),
        "r2": round(float(m._r2), 4),
        "n_areas": int(df["area"].nunique()),
        "window": [
            str(df["sale_date"].min().date()),
            str(df["sale_date"].max().date()),
        ],
    }
    (PROCESSED / "model_stats.json").write_text(json.dumps(stats, indent=1))
    print(report)


if __name__ == "__main__":
    main()

"""Fit the hedonic price model and extract block-group price factors.

log(price) ~ house attributes + year-quarter FE + area effect,
where the area effect is a block-group dummy (pooled up to tract when a
block group has too few sales). The exported price factor is
exp(area effect), normalized so the sales-weighted average is 1.0.

Outputs:
  data/processed/factors.parquet  (one row per area unit)
  data/processed/diagnostics.md
"""

import json

import numpy as np
import pandas as pd
import pyfixest as pf

from .config import MIN_SALES_PER_BG, PROCESSED


def prepare() -> pd.DataFrame:
    df = pd.read_parquet(PROCESSED / "sales_geo.parquet")
    n0 = len(df)
    df = df.dropna(subset=["bg_geoid", "sqft", "sale_price", "year_built"])
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
    coefs, ses = m.coef(), m.se()
    areas = sorted(df["area"].unique())
    ref = areas[0]  # dropped dummy: effect 0 by construction
    fe = {ref: 0.0}
    se = {ref: 0.0}
    for a in areas[1:]:
        key = f"C(area)[T.{a}]"
        fe[a] = coefs[key]
        se[a] = ses[key]

    out = pd.DataFrame(
        {"area": areas, "fe": [fe[a] for a in areas], "se": [se[a] for a in areas]}
    )
    # normalize: sales-weighted mean effect = 0 -> factor 1.0 = metro average
    w = df["area"].value_counts()
    out["n_sales"] = out["area"].map(w)
    mean_fe = np.average(out["fe"], weights=out["n_sales"])
    out["factor"] = np.exp(out["fe"] - mean_fe)
    out["factor_lo"] = np.exp(out["fe"] - 1.96 * out["se"] - mean_fe)
    out["factor_hi"] = np.exp(out["fe"] + 1.96 * out["se"] - mean_fe)

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


def main() -> None:
    df = prepare()
    m = fit(df)
    factors = extract_factors(m, df)
    factors.to_parquet(PROCESSED / "factors.parquet", index=False)
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

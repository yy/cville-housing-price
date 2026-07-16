"""Per-era price factors for the time slider.

Fits the same hedonic spec as the headline model separately for each era in
config.ERAS (per-era block-group pooling with the same MIN_SALES_PER_BG rule,
per-era normalization to a sales-weighted geometric mean of 1.0), then
expands each era's area units to every block group the same way export.py
does (BG -> pooled tract -> locality).

Output: site/data/eras.json
  { "eras": [{key, label, window, n_sales, r2, n_areas}, ...],
    "areas": { "<GEOID>": { "<era key>": {factor, lo, hi, pooled} | null } } }
"""

import json

import numpy as np

from .config import ERAS, SITE_DATA
from .export import load_bg
from .model import extract_factors, fit, prepare


def era_bg_table(factors, bg) -> dict:
    """Expand area-unit factors to one record per block group (or None)."""
    lookup = {r["area"]: r for _, r in factors.iterrows()}
    out = {}
    for _, g in bg.iterrows():
        geoid, loc = g["GEOID"], g["locality"]
        rec = None
        for key, pooled in ((geoid, 0), ("T" + geoid[:11], 1), ("L" + loc, 1)):
            if key in lookup:
                r = lookup[key]
                rec = {
                    "factor": round(float(r["factor"]), 3),
                    "lo": round(float(r["factor_lo"]), 3),
                    "hi": round(float(r["factor_hi"]), 3),
                    "pooled": pooled,
                }
                break
        out[geoid] = rec
    return out


def main() -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    bg = load_bg()
    eras_meta = []
    per_era_bg = {}
    era_factors = {}

    for era in ERAS:
        df = prepare(start=era["start"], end=era["end"])
        m = fit(df)
        factors = extract_factors(m, df)
        era_factors[era["key"]] = factors
        eras_meta.append(
            {
                "key": era["key"],
                "label": era["label"],
                "window": [
                    str(df["sale_date"].min().date()),
                    str(df["sale_date"].max().date()),
                ],
                "n_sales": int(m._N),
                "r2": round(float(m._r2), 4),
                "n_areas": int(df["area"].nunique()),
            }
        )
        per_era_bg[era["key"]] = era_bg_table(factors, bg)
        print(
            f"era {era['key']}: N={int(m._N)}, R²={m._r2:.3f}, "
            f"{df['area'].nunique()} areas, factor "
            f"{factors['factor'].min():.2f}-{factors['factor'].max():.2f}"
        )

    areas = {
        geoid: {era["key"]: per_era_bg[era["key"]][geoid] for era in ERAS}
        for geoid in bg["GEOID"]
    }
    out = {"eras": eras_meta, "areas": areas}
    (SITE_DATA / "eras.json").write_text(json.dumps(out))

    # cross-era diagnostics: pre/post correlation and city/county discount
    keys = [e["key"] for e in ERAS]
    if len(keys) >= 2:
        a, b = keys[0], keys[-1]
        fa = {g: r["factor"] for g, r in per_era_bg[a].items() if r}
        fb = {g: r["factor"] for g, r in per_era_bg[b].items() if r}
        common = sorted(set(fa) & set(fb))
        if len(common) > 2:
            r = np.corrcoef([fa[g] for g in common], [fb[g] for g in common])[0, 1]
            print(f"BG factor correlation {a} vs {b}: r={r:.3f} (n={len(common)})")
    for key, factors in era_factors.items():
        med = factors.groupby("locality").apply(
            lambda d: np.average(np.log(d["factor"]), weights=d["n_sales"]),
            include_groups=False,
        )
        if {"cville", "albemarle"} <= set(med.index):
            gap = np.exp(med["cville"] - med["albemarle"]) - 1
            print(f"era {key}: city vs county factor gap {gap:+.1%}")
    print(f"wrote eras.json with {len(areas)} block groups, {len(ERAS)} eras")


if __name__ == "__main__":
    main()

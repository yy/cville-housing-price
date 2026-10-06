"""Regression coverage for observations dropped by the model."""

import json

import numpy as np
import pandas as pd

from pipeline import model


def test_main_uses_fitted_sample_when_quarter_is_singleton(monkeypatch, tmp_path):
    rng = np.random.default_rng(42)
    n = 120
    area = np.tile(["A", "B", "C"], n // 3)
    quarter = np.tile(["2023Q1", "2023Q2"], n // 2)
    log_sqft = rng.normal(7.2, 0.3, n)
    age = rng.uniform(5, 80, n)
    df = pd.DataFrame(
        {
            "area": area,
            "yq": quarter,
            "log_sqft": log_sqft,
            "beds": rng.integers(2, 6, n),
            "baths": rng.uniform(1, 4, n),
            "age": age,
            "age2": age**2 / 100,
            "log_acre": rng.uniform(0, 1, n),
            "stories": rng.uniform(1, 3, n),
            "ptype": rng.choice(["detached", "townhouse"], n),
            "grade": rng.choice(["good", "fair"], n),
            "sqft": np.exp(log_sqft),
            "sale_date": pd.Timestamp("2023-01-01"),
            "lon": rng.uniform(-78.6, -78.4, n),
            "lat": rng.uniform(38.0, 38.2, n),
            "locality": "cville",
        }
    )
    df["log_price"] = (
        5
        + log_sqft
        + pd.Series(area).map({"A": 0, "B": 0.2, "C": -0.1})
        + rng.normal(0, 0.1, n)
    )
    df["sale_price"] = np.exp(df["log_price"])
    singleton = df.iloc[[0]].copy()
    singleton["yq"] = "2099Q1"
    singleton["sale_date"] = pd.Timestamp("2099-01-01")
    df = pd.concat([df.iloc[: n // 2], singleton, df.iloc[n // 2 :]], ignore_index=True)

    monkeypatch.setattr(model, "prepare", lambda: df)
    monkeypatch.setattr(model, "PROCESSED", tmp_path)
    model.main()

    locations = pd.read_parquet(tmp_path / "sale_loc.parquet")
    factors = pd.read_parquet(tmp_path / "factors.parquet")
    stats = json.loads((tmp_path / "model_stats.json").read_text())
    assert len(locations) == n
    assert not (locations["sale_date"] == pd.Timestamp("2099-01-01")).any()
    assert factors["n_sales"].sum() == n
    assert stats["n_sales"] == n

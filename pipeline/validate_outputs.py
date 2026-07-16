"""Validate generated map data before deployment."""

import json
import math

from .config import PROCESSED, SITE_DATA


def reject_constant(value: str):
    raise ValueError(f"non-finite JSON value {value}")


def load(name: str) -> dict:
    path = SITE_DATA / name
    with path.open() as f:
        return json.load(f, parse_constant=reject_constant)


def validate_geojson(name: str, required_property: str | None = None) -> None:
    data = load(name)
    if data.get("type") != "FeatureCollection" or not data.get("features"):
        raise ValueError(f"{name} is not a non-empty GeoJSON FeatureCollection")
    if required_property is not None:
        values = [
            feature.get("properties", {}).get(required_property)
            for feature in data["features"]
        ]
        if not any(value is not None for value in values):
            raise ValueError(f"{name} has no non-null {required_property} values")


def validate_finite(value, path: str = "root") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite number at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            validate_finite(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_finite(child, f"{path}[{index}]")


def main() -> None:
    validate_geojson("factors.geojson", "factor")
    validate_geojson("localities.geojson", "locality")
    validate_geojson("surface.geojson", "factor_fine")
    validate_geojson("zori.geojson", "zori")

    meta = load("meta.json")
    required = {"n_sales", "r2", "window", "built", "ref_price"}
    missing = required - set(meta)
    if missing:
        raise ValueError(f"meta.json is missing {sorted(missing)}")

    insight = load("insight.json")
    if not insight.get("bgs") or not insight.get("curves"):
        raise ValueError("insight.json has no block groups or curves")

    eras = load("eras.json")
    if not eras.get("eras") or not eras.get("areas"):
        raise ValueError("eras.json has no eras or areas")

    for name in ("meta.json", "insight.json", "eras.json"):
        validate_finite(load(name), name)

    stamp = PROCESSED / "site.validated"
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text("ok\n")
    print(f"validated {SITE_DATA}")


if __name__ == "__main__":
    main()

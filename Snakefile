from pipeline.config import ACS_RENT_TABLES, ACS_YEAR


RAW = "data/raw"
REFERENCE = "data/reference"
PROCESSED = "data/processed"
SITE_DATA = "site/data"
ENV = ["pyproject.toml", "uv.lock"]

CVILLE_RAW = [
    f"{RAW}/cville_sales.json",
    f"{RAW}/cville_residential.json",
    f"{RAW}/cville_base.json",
    f"{RAW}/cville_assessments.json",
    f"{RAW}/cville_parcels.geojson",
]
ALBEMARLE_RAW = [
    f"{RAW}/alb_sales.zip",
    f"{RAW}/alb_cards.zip",
    f"{RAW}/alb_parcel_info.zip",
    f"{RAW}/alb_other_chars.zip",
    f"{RAW}/alb_parcels_shape.zip",
    f"{RAW}/alb_compplan.zip",
]
CENSUS_RAW = [
    f"{RAW}/tiger_bg.zip",
    f"{RAW}/tiger_tract.zip",
    f"{RAW}/tiger_puma.zip",
    f"{RAW}/tiger_zcta.zip",
]
ACS_REFERENCE = [
    f"{REFERENCE}/acs_{ACS_YEAR}_{table}_bg.csv" for table in ACS_RENT_TABLES
]
OTHER_RAW = [f"{RAW}/zori_zip.csv", f"{RAW}/pums_hva.zip"]
ALL_RAW = CVILLE_RAW + ALBEMARLE_RAW + CENSUS_RAW + OTHER_RAW

SITE_OUTPUTS = [
    f"{SITE_DATA}/factors.geojson",
    f"{SITE_DATA}/localities.geojson",
    f"{SITE_DATA}/insight.json",
    f"{SITE_DATA}/meta.json",
    f"{SITE_DATA}/surface.geojson",
    f"{SITE_DATA}/zori.geojson",
    f"{SITE_DATA}/eras.json",
]


rule all:
    input:
        f"{PROCESSED}/site.validated"


rule fetch_all:
    input:
        ALL_RAW + ACS_REFERENCE


rule fetch_cville:
    input:
        "pipeline/fetch.py",
        "pipeline/config.py",
        *ENV,
    output:
        CVILLE_RAW
    shell:
        "uv run python -m pipeline.fetch --group cville --force"


rule fetch_albemarle:
    input:
        "pipeline/fetch.py",
        "pipeline/config.py",
        *ENV,
    output:
        ALBEMARLE_RAW
    shell:
        "uv run python -m pipeline.fetch --group albemarle --force"


rule fetch_census:
    input:
        "pipeline/fetch.py",
        "pipeline/config.py",
        *ENV,
    output:
        CENSUS_RAW
    shell:
        "uv run python -m pipeline.fetch --group census --force"


rule fetch_zori:
    input:
        "pipeline/fetch.py",
        "pipeline/config.py",
        *ENV,
    output:
        f"{RAW}/zori_zip.csv"
    shell:
        "uv run python -m pipeline.fetch --group zori --force"


rule fetch_pums:
    input:
        "pipeline/fetch.py",
        "pipeline/config.py",
        *ENV,
    output:
        f"{RAW}/pums_hva.zip"
    shell:
        "uv run python -m pipeline.fetch --group pums --force"


rule clean:
    input:
        CVILLE_RAW[:4]
        + ALBEMARLE_RAW[:3]
        + ["pipeline/clean.py", "pipeline/config.py"]
        + ENV
    output:
        f"{PROCESSED}/sales.parquet"
    shell:
        "uv run python -m pipeline.clean"


rule join_geo:
    input:
        f"{PROCESSED}/sales.parquet",
        f"{RAW}/cville_parcels.geojson",
        f"{RAW}/alb_parcels_shape.zip",
        f"{RAW}/tiger_bg.zip",
        "pipeline/join_geo.py",
        "pipeline/config.py",
        *ENV,
    output:
        f"{PROCESSED}/sales_geo.parquet"
    shell:
        "uv run python -m pipeline.join_geo"


rule model:
    input:
        f"{PROCESSED}/sales_geo.parquet",
        "pipeline/model.py",
        "pipeline/config.py",
        *ENV,
    output:
        f"{PROCESSED}/factors.parquet",
        f"{PROCESSED}/sale_loc.parquet",
        f"{PROCESSED}/diagnostics.md",
        f"{PROCESSED}/model_stats.json",
    shell:
        "uv run python -m pipeline.model"


rule rent:
    input:
        ACS_REFERENCE
        + [
            f"{RAW}/pums_hva.zip",
            f"{RAW}/tiger_puma.zip",
            f"{RAW}/tiger_bg.zip",
            f"{RAW}/zori_zip.csv",
            f"{RAW}/tiger_zcta.zip",
            "pipeline/rent.py",
            "pipeline/config.py",
        ]
        + ENV
    output:
        f"{PROCESSED}/rent_bg.parquet",
        f"{SITE_DATA}/zori.geojson",
    shell:
        "uv run python -m pipeline.rent"


rule surface:
    input:
        f"{PROCESSED}/sale_loc.parquet",
        f"{RAW}/tiger_bg.zip",
        "pipeline/surface.py",
        "pipeline/config.py",
        *ENV,
    output:
        f"{SITE_DATA}/surface.geojson"
    shell:
        "uv run python -m pipeline.surface"


rule export:
    input:
        f"{PROCESSED}/factors.parquet",
        f"{PROCESSED}/sales_geo.parquet",
        f"{PROCESSED}/model_stats.json",
        f"{PROCESSED}/rent_bg.parquet",
        f"{RAW}/tiger_bg.zip",
        "pipeline/export.py",
        "pipeline/config.py",
        *ENV,
    output:
        f"{SITE_DATA}/factors.geojson",
        f"{SITE_DATA}/localities.geojson",
        f"{SITE_DATA}/insight.json",
        f"{SITE_DATA}/meta.json",
    shell:
        "uv run python -m pipeline.export"


rule eras:
    input:
        f"{PROCESSED}/sales_geo.parquet",
        f"{RAW}/tiger_bg.zip",
        "pipeline/eras.py",
        "pipeline/model.py",
        "pipeline/export.py",
        "pipeline/config.py",
        *ENV,
    output:
        f"{SITE_DATA}/eras.json"
    shell:
        "uv run python -m pipeline.eras"


rule validate_outputs:
    input:
        SITE_OUTPUTS
        + ["pipeline/validate_outputs.py", "pipeline/config.py"]
        + ENV
    output:
        f"{PROCESSED}/site.validated"
    shell:
        "uv run python -m pipeline.validate_outputs"

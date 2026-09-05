"""Shared paths, URLs, and constants for the pipeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
REFERENCE = ROOT / "data" / "reference"
MANUAL = ROOT / "data" / "manual"
PROCESSED = ROOT / "data" / "processed"
SITE_DATA = ROOT / "site" / "data"

STATE_FIPS = "51"
CITY_FIPS = "540"  # Charlottesville City
COUNTY_FIPS = "003"  # Albemarle County

# Charlottesville ArcGIS REST tables (OpenData_2 MapServer)
CVILLE_ARCGIS = "https://gisweb.charlottesville.org/arcgis/rest/services"
CVILLE_TABLES = {
    "cville_sales": f"{CVILLE_ARCGIS}/OpenData_2/MapServer/3",
    "cville_residential": f"{CVILLE_ARCGIS}/OpenData_2/MapServer/17",
    "cville_base": f"{CVILLE_ARCGIS}/OpenData_2/MapServer/20",
    "cville_assessments": f"{CVILLE_ARCGIS}/OpenData_2/MapServer/1",
}
# Parcel polygons (OpenData_1 MapServer layer 43: Parcel Boundary Area)
CVILLE_PARCELS_LAYER = f"{CVILLE_ARCGIS}/OpenData_1/MapServer/43"

# Albemarle County direct downloads (updated weekly)
ALBEMARLE_FILES = {
    "alb_sales": "https://albgis.albemarle.org/gisdata/CAMA/GIS_View_Redacted_VisionSales_TXT.zip",
    "alb_cards": "https://albgis.albemarle.org/gisdata/CAMA/GIS_CardLevelData_new_TXT.zip",
    "alb_parcel_info": "https://albgis.albemarle.org/gisdata/CAMA/GIS_View_Redacted_ParcelInfo_TXT.zip",
    "alb_other_chars": "https://albgis.albemarle.org/gisdata/CAMA/CityView_View_OtherParcelCharacteristics_TXT.zip",
    "alb_parcels_shape": "https://albgis.albemarle.org/gisdata/Parcels/shape/parcels_shape_current.zip",
    "alb_compplan": "https://albgis.albemarle.org/gisdata/CompPlan/Comp_Plan_Areas.zip",
}

# Census TIGER/Line boundaries
TIGER_FILES = {
    "tiger_bg": "https://www2.census.gov/geo/tiger/TIGER2024/BG/tl_2024_51_bg.zip",
    "tiger_tract": "https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_51_tract.zip",
    "tiger_puma": "https://www2.census.gov/geo/tiger/TIGER2024/PUMA20/tl_2024_51_puma20.zip",
    "tiger_zcta": "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip",
}

# Zillow Observed Rent Index, ZIP level, smoothed, all homes+multifamily
ZORI_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zori/"
    "Zip_zori_uc_sfrcondomfr_sm_month.csv"
)

# ACS PUMS 5-year housing file for Virginia
PUMS_URL = (
    "https://www2.census.gov/programs-surveys/acs/data/pums/2023/5-Year/csv_hva.zip"
)

# ACS API
ACS_YEAR = 2023
ACS_BASE = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"
ACS_TABLE_URL = (
    f"https://www2.census.gov/programs-surveys/acs/summary_file/{ACS_YEAR}/"
    f"table-based-SF/data/5YRData/acsdt5y{ACS_YEAR}-{{table}}.dat"
)
ACS_RENT_TABLES = ["b25064", "b25042", "b25032", "b25037", "b25003"]


def acs_table_path(table: str) -> Path:
    """Return the tracked local snapshot path for an ACS table."""
    return REFERENCE / f"acs_{ACS_YEAR}_{table}_bg.csv"


# Modeling window. Pre- and post-pandemic factor maps differ materially
# (r≈0.67 across block groups; the city's ~18% discount vs the county closed
# to a slight premium), so the headline model uses post-shock sales only.
# Cleaning keeps a longer window (CLEAN_START) so per-era factors can be fit
# from one cleaned dataset.
CLEAN_START = "2018-01-01"
SALES_START = "2023-01-01"
MIN_SALES_PER_BG = 20

# Ordered eras for the time-slider factor maps (last = headline window).
# `end` is inclusive; None = open-ended.
ERAS = [
    {"key": "2018-19", "label": "2018–19", "start": "2018-01-01", "end": "2019-12-31"},
    {"key": "2023+", "label": "2023+", "start": SALES_START, "end": None},
]

# Mortgage assumptions for the $/month translation
MORTGAGE_RATE = 0.065  # 30-year fixed, annual
DOWN_PAYMENT = 0.20
TERM_YEARS = 30

# Job-center anchors for distance/commute analysis (lon, lat)
DOWNTOWN = (-78.4769, 38.0293)  # Downtown Mall
UVA = (-78.5034, 38.0355)  # Rotunda

# Commute-cost assumptions (single commuter, workdays only)
COST_PER_MILE = 0.70  # IRS-style all-in vehicle cost per mile
COMMUTE_DAYS_PER_MONTH = 22
BIKE_RANGE_MI = 3.0  # classic-bike comfort radius (chart context only)
EBIKE_RANGE_MI = 6.0  # e-bike comfort radius (chart context only)

# Fine-grained smoothed surface
SURFACE_CELL_M = 500  # grid cell size
SURFACE_BW_M = 800  # gaussian kernel bandwidth
SURFACE_MIN_N = 8  # min effective sample per cell

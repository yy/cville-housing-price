"""Shared paths, URLs, and constants for the pipeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
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

# Modeling window
SALES_START = "2018-01-01"
MIN_SALES_PER_BG = 20

# cville-housing-price

Quality-adjusted housing price index for Charlottesville City and Albemarle County, VA.

**Live map:** https://yy.github.io/cville-housing-price/ ·
[methodology](https://yy.github.io/cville-housing-price/methodology.html)

A hedonic model predicts each sale price from visible attributes (size, age, rooms,
lot, condition); the census-block-group fixed effect is the **price factor** — how much
more or less the same house costs in that area relative to the metro-wide expectation.
Rent layers come from ACS, Zillow ZORI, and HUD Small Area FMRs, plus a
characteristics-adjusted rent factor built from ACS PUMS.

## Data sources

- Charlottesville Open Data (ArcGIS REST): sales, residential details, parcel base data
- Albemarle County GIS (`albgis.albemarle.org`): transfer history, card-level CAMA data,
  parcel-level data, parcels shapefile
- Census: TIGER/Line boundaries, ACS tables, PUMS microdata
- Zillow ZORI (ZIP-level rent index)
- HUD Small Area FMR (manual download into `data/manual/`, optional)

## Usage

```bash
make fetch    # download raw data into data/raw/
make build    # clean → join → model → rent → export site/data/
make serve    # local preview at http://localhost:8321
```

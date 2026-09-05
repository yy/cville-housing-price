# cville-housing-price

Quality-adjusted housing price index for Charlottesville City and Albemarle County, VA.

**Live map:** https://yyahn.com/cville-housing-price/ ·
[methodology](https://yyahn.com/cville-housing-price/methodology.html)

A hedonic model predicts each sale price from visible attributes (size, age, rooms,
lot, condition); the census-block-group fixed effect is the **price factor** — how much
more or less the same house costs in that area relative to the metro-wide expectation
(normalized so the sales-weighted *geometric* mean factor is 1.00, i.e. 1.00 = the
typical location). A time slider compares the current (2023+) factor map with a
pre-pandemic (2018–19) fit of the same model.
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
make fetch    # download any missing raw inputs
make build    # build only missing or outdated outputs with Snakemake
make refresh  # refresh city, county, and ZORI data, then rebuild affected outputs
make refresh-acs # update tracked ACS snapshots after changing ACS_YEAR
make validate # validate every generated map-data file
make serve    # local preview at http://localhost:8321
```

The default Snakemake target builds and validates every file under `site/data/`.
Raw and processed data remain gitignored. Filtered ACS block-group tables are
year-versioned under `data/reference/` and tracked in Git; update `ACS_YEAR` and run
`make refresh-acs` only when adopting a new ACS vintage. The GitHub Pages workflow
performs a clean build on every push to `main`, on manual dispatch, and weekly, while
scheduled deployments fetch the current non-ACS inputs.

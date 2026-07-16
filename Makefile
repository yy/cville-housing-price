.PHONY: fetch refresh build model export validate serve

SNAKEMAKE = uv run snakemake --cores 2

fetch:
	$(SNAKEMAKE) fetch_all

refresh:
	uv run python -m pipeline.fetch --group cville --group albemarle --group zori --force
	$(SNAKEMAKE)

build:
	$(SNAKEMAKE)

model:
	$(SNAKEMAKE) data/processed/factors.parquet

export:
	$(SNAKEMAKE) site/data/meta.json

validate:
	$(SNAKEMAKE) data/processed/site.validated

serve:
	uv run python -m http.server 8321 -d site

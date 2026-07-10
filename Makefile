.PHONY: fetch build model export serve

fetch:
	uv run python -m pipeline.fetch

build:
	uv run python -m pipeline.clean
	uv run python -m pipeline.join_geo
	uv run python -m pipeline.model
	uv run python -m pipeline.rent
	uv run python -m pipeline.surface
	uv run python -m pipeline.export

model:
	uv run python -m pipeline.model

export:
	uv run python -m pipeline.export

serve:
	python3 -m http.server 8321 -d site

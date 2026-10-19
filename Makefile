.PHONY: setup test lint run demo avaliar avaliar-demo docker

setup:
	uv sync

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

run:
	uv run bot servir

demo:
	BOT_MODO_DEMO=true uv run bot servir

avaliar:
	uv run bot avaliar --saida avaliacao/resultados/ultima.json

avaliar-demo:
	uv run bot avaliar --demo --minimo 0.9

docker:
	docker compose up --build

.PHONY: dev build test migrate docker-up docker-down clean chaos

dev:
	uvicorn api.main:app --reload --port 8002

build:
	docker compose build

test:
	python -m pytest tests/ -v

chaos:
	python chaos/chaos_runner.py --all

chaos-redis:
	python chaos/chaos_runner.py --scenario redis

chaos-postgres:
	python chaos/chaos_runner.py --scenario postgres

migrate:
	alembic upgrade head

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	rm -rf __pycache__ */__pycache__ */*/__pycache__
	rm -rf .pytest_cache
	rm -rf *.egg-info
	find . -name "*.pyc" -delete

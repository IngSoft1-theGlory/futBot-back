.PHONY: install run dev test docker-up docker-down docker-logs

include .env

install:
	pip install -r requirements.txt

run:
	uvicorn src.main:app --host 0.0.0.0 --port 8000

dev:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -v

docker-up:
	docker compose up --build -d db

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f backend

test:
	PYTHONPATH=. pytest tests/ -v

test-postgres:
	docker compose up -d db
	TEST_DATABASE_URL=postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:5432/$(POSTGRES_DB) PYTHONPATH=. pytest tests/ -v
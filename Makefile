.PHONY: install run dev test docker-up docker-down docker-logs migrate makemigrations downgrade

-include .env

install:
	pip install -r requirements.txt

run:
	uvicorn src.main:app --host 0.0.0.0 --port 8000

dev:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

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

# Aplica migraciones pendientes, correr después de pullear cambios de otro.
migrate:
	PYTHONPATH=. alembic upgrade head

# Genera un borrador de migración a partir del diff entre los modelos y
# la DB actual. SIEMPRE revisar el script generado a mano antes de
# commitear.
makemigrations:
	PYTHONPATH=. alembic revision --autogenerate -m "$(m)"

# Revierte migraciones. Por default retrocede un solo paso 
# útil para descartar una migración de prueba. Para ir a un
# punto puntual: make downgrade rev=<revision_id>. Para vaciar el
# esquema entero: make downgrade rev=base.
downgrade:
	PYTHONPATH=. alembic downgrade $(if $(rev),$(rev),-1)
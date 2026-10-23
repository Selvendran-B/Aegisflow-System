.PHONY: up down reset ps logs db-init seed data verify test lint clean

up:
	docker compose up -d

down:
	docker compose down

reset:
	docker compose down -v
	docker compose up -d

ps:
	docker compose ps

logs:
	docker compose logs -f

db-init:
	docker compose exec postgres psql -U $${DB_USER:-aegis} -d $${DB_NAME:-aegisflow} -f /docker-entrypoint-initdb.d/01_init.sql

seed:
	python scripts/seed_db.py

data:
	python scripts/download_datasets.py

verify:
	python scripts/verify_m1.py

test:
	pytest -q

lint:
	ruff check .

clean:
	docker compose down -v
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +




# ---- M2 targets: append below the M1 block. RECIPEPREFIX applies only to rules
# written after it, so M1's tab-indented rules keep working. ----
.RECIPEPREFIX = >
PY ?= python
M2_PATH := PYTHONPATH=services/ingestion/src:ml/src:.
M2_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.m2.yml

up-m2:
> $(M2_COMPOSE) up -d --build ingestion graph-job
migrate:
> $(M2_PATH) alembic upgrade head
seed-fraud:
> $(M2_PATH) $(PY) db/seed/seed_known_fraud.py
ingest:
> $(M2_PATH) uvicorn ingestion.main:app --reload --port 8001
graph-once:
> $(M2_PATH) $(PY) -m aegis_ml.features.graph_features --once
features-pit:
> dvc repro features_pit
parity:
> $(M2_PATH) PARITY_REDIS_URL=redis://localhost:6379/15 pytest -q tests/m2/unit/test_m2_parity.py
test-m2:
> $(M2_PATH) pytest -q tests/m2/unit tests/m2/api
test-m2-int:
> $(M2_PATH) pytest -q tests/m2/integration
verify-m2:
> $(M2_PATH) $(PY) scripts/verify_m2.py
m2: test-m2 test-m2-int verify-m2
.PHONY: up-m2 migrate seed-fraud ingest graph-once \
         features-pit parity test-m2 test-m2-int verify-m2 m2

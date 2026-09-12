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
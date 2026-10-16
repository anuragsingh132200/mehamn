.PHONY: up test evaluate frontend-build
up:
	docker compose up --build
test:
	cd backend && .venv/bin/pytest -q
evaluate:
	backend/.venv/bin/python scripts/evaluate.py
frontend-build:
	cd frontend && npm run build

# Repository Guidelines

## Project Structure & Module Organization

This repository contains a Vietnamese legal RAG system with a Python backend and a Next.js frontend. Core entry points are `app.py`, `main.py`, and `mcp_server.py`. Backend modules are grouped by responsibility: `api/` for FastAPI endpoints, `core/` for classification, embeddings, parsing, RAG orchestration, health, and security, `db/` for Qdrant/Redis/SQLite access, `retrievers/` for search adapters, `schemas/` for shared models, and `tools/` for LLM clients. Scripts live in `scripts/`, deployment assets in `deploy/`, docs in `docs/`, runtime data in `artifacts/`, `result/`, `qdrant_data/`, and `sqlite_data/`, and frontend code in `frontend/src/`.

## Build, Test, and Development Commands

Create and activate a Python environment, then install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Start infrastructure with `docker compose up -d` for Qdrant, Redis, and Postgres. Load legal data with `python indexer.py`. Run the backend with `uvicorn app:app --host 0.0.0.0 --port 8000 --reload` or `python app.py`; API docs are at `http://localhost:8000/docs`. For CLI smoke, use `python main.py`. In `frontend/`, run `npm install`, `npm run dev`, `npm run build`, and `npm run lint`.

## Coding Style & Naming Conventions

Use Python 3.12-compatible code, 4-space indentation, typed signatures where practical, and descriptive snake_case names. Keep provider-specific LLM code in `tools/` and shared RAG behavior in `core/`. Frontend files use TypeScript/React conventions: PascalCase components, camelCase hooks/utilities, and app routes under `frontend/src/app/`. Before editing Next.js code, consult `frontend/AGENTS.md` and the local docs in `frontend/node_modules/next/dist/docs/`.

## Testing Guidelines

Pytest is configured in `pytest.ini` with `testpaths = tests` and discovery via `test_*.py`, `Test*`, and `test_*`. Run all backend tests with `pytest`; target a file with `pytest tests/test_api.py`. Add tests for API behavior, security rules, retrieval ranking, provider fallbacks, and indexer changes. Mark integration tests clearly when they require Docker services or external API keys.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commits with optional scopes, such as `feat(21): ...` and `docs(state): ...`. Follow `type(scope): concise imperative summary`, using `feat`, `fix`, `docs`, `test`, or `chore`. Pull requests should describe behavior changes, list verification commands, mention required environment variables or services, link related issues/plans, and include screenshots for UI changes.

## Security & Configuration Tips

Do not commit real secrets from `.env`, `.env.local`, or provider dashboards. Start from `.env.example`, keep API keys local, and document new configuration keys there. Treat `sqlite_data/`, `qdrant_data/`, cache folders, and generated outputs as local runtime artifacts unless a change intentionally updates sample assets.

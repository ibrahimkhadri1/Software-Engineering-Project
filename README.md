# Canvas Autograder

An AI-assisted grading tool for Canvas, built by team iCANDY for CMPE 131 (Fall 2026). A professor or TA picks a
Canvas assignment and a rubric, the system suggests a score and feedback for each submission using Amazon Bedrock,
and staff review, edit or reject every suggestion. Only approved grades are published to Canvas.

- **Frontend:** React + TypeScript + Vite (`frontend/`)
- **Backend:** FastAPI + SQLAlchemy + PostgreSQL (`backend/`)
- **Services:** Auth0 (sign-in), Canvas REST API, Amazon Bedrock (Claude Sonnet 4.5)

## Run it locally

Requirements: [Docker Desktop](https://www.docker.com/products/docker-desktop/),
[uv](https://docs.astral.sh/uv/) (Python 3.13), Node.js 24.

```sh
# 1. Database (from the repo root)
docker compose up -d --wait db

# 2. Backend
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# 3. Frontend (second terminal)
cd frontend
cp .env.example .env.local
npm install
npm run dev                 # http://localhost:5173
```

Check: `http://localhost:8000/healthz` returns `{"status": "ok"}` and the page at `http://localhost:5173` shows
"Server: ok".

## Tests

```sh
(cd backend && uv run pytest)              # unit tests with coverage
(cd frontend && npm run lint && npm run build)
```

CI runs both on every pull request.

## Configuration

Settings come from environment variables (`backend/.env`, `frontend/.env.local`); see the `.env.example` files.

## Contributing

Work on a branch and open a pull request to `main`; changes are reviewed before merging. Report defects as GitHub
Issues.

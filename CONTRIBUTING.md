# Contributing

## Branches
- One branch per feature, named by kind: `feature/<name>`, `fix/<name>`, `docs/<name>`, `chore/<name>`.
- Keep working in the feature's own branch until it is merged; start a new branch only for a new feature.
- Open a pull request into `main`; CI must pass (`pytest`, migration check on SQLite and Postgres).

## Local setup
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head && python -m scripts.seed
pytest
uvicorn app.main:app --reload
```
Always activate the virtual environment (`source venv/bin/activate`) in a new terminal first.

## Database changes
Edit `app/models.py`, run `alembic revision --autogenerate -m "what changed"`, review the file in `migrations/versions/`, and run `alembic upgrade head`. New enum values on Postgres need an `ALTER TYPE ... ADD VALUE` step (see `0005`).

## Releases
`git tag v0.2.0 && git push origin v0.2.0` builds the Docker image and publishes a GitHub Release (see `.github/workflows/release.yml`).

# Python FastAPI Template

This project is a microservice application template based on FastAPI. It includes SQLAlchemy (Async), Pydantic, and a
Repository pattern with DDD elements. It requires **Python 3.14**.

## Key Features

- **FastAPI**: Modern, fast Python web framework.
- **Asynchronous SQLAlchemy**: Asynchronous DB engine and session management (supports writer/reader routing).
- **Repository Pattern**: Decouples data access layer to maintain business logic purity.
- **MongoDB Repository**: A document repository on PyMongo's async API (`AsyncMongoClient`).
- **Idempotency Cache**: Async and sync in-process caches that run a request once per idempotency key and reject
  concurrent duplicates with `409`.
- **Environment-based Configuration**: Separated local, dev, and prod environments using `pydantic-settings`.
- **Middleware & Exception Handling**: Includes response logs, a per-request DB session scope, and common exception
  handlers.

## Project Structure

```text
.
├── api/                    # API routers and versioning
├── app/
│   ├── core/
│   │   ├── cache/          # Idempotency caches (async, sync)
│   │   ├── config/         # Settings per environment
│   │   ├── db/             # SQL session, transactions, repositories
│   │   │   ├── sql/        # SQLAlchemy repository
│   │   │   └── nosql/      # MongoDB client and repository
│   │   ├── exception/      # Exception types and handlers
│   │   ├── fastapi/        # Middleware and logging setup
│   │   └── utils/          # Singleton, background task owner
│   ├── user/               # Example domain (model, schemas)
│   └── server.py           # Application factory and lifespan
├── scripts/                # Helper scripts (test environment)
├── main.py                 # Application entry point
└── tests/                  # Test cases
```

## Getting Started

### 1. Install Dependencies

Use a Python 3.14 interpreter (`.python-version` pins it for pyenv and uv).

```bash
pip install -r requirements.txt
```

For development (tests, ruff, mypy), install the project with its `dev` dependency group (pip 25.1 or later):

```bash
pip install -e . --group dev
```

### 2. Configure

The `ENV` environment variable selects the settings: `local` (default), `dev` or `prod`. It is read from the process
environment only; an `ENV` line in an env file is ignored. Each environment reads its own file (`.env.local`, `.env.dev`,
`.env.prod`); copy `.env.example` and fill in what you need.

- `local` uses an in-memory SQLite database unless `DATABASE_URL` is set.
- `dev` and `prod` require `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_USER`, `DATABASE_PASSWORD` and `DATABASE_NAME`
  and connect to MariaDB through `aiomysql`.
- `DATABASE_READ_URL` adds a read replica.
- `MONGO_URL` enables MongoDB: the client is available as `request.state.mongo`. With `MONGO_DATABASE` also set, that
  database is available as `request.state.mongo_db`.
- `CORS_ALLOW_ORIGINS` is a JSON list of allowed origins.

### 3. Run Application

Run via `main.py` and specify the environment using the `--env` option (default: `local`). `--debug` sets `DEBUG=true`,
which turns on the per-response debug log lines; without it the environment's own `DEBUG` applies (`local` and `dev`
default to `true`, `prod` to `false`).

```bash
python main.py --env local --debug
```

`main.py` starts uvicorn with the application factory. To start uvicorn yourself, set `ENV` and pass `--factory`:

```bash
ENV=local uvicorn app.server:init_app --factory
```

### 4. API Documentation

After running the server, you can access the Swagger documentation at:

- Swagger UI: `http://127.0.0.1:8080/swagger_ui`
- ReDoc: `http://127.0.0.1:8080/redoc`

With `ENV=prod`, the documentation pages and `/openapi.json` are disabled.

## Limitations

- The idempotency cache lives in each process's memory. With several workers (`prod` runs 4), a retry that reaches
  another worker runs again. Use a shared store such as Redis for real deployments.
- Secret arguments (`SecretStr`, `SecretBytes`, `Secret`) enter the idempotency key through an HMAC under a random salt
  created when the process starts. Keys for calls that carry secrets therefore match only within one process and change
  on restart. If the cache moves to a shared store, the salt must come from settings instead.
- Every worker runs `create_all` at startup. That is fine for a template; use migrations (for example Alembic) in
  production.

## Running Tests

```bash
pytest
```

The MongoDB repository tests run only when `MONGO_TEST_URL` is set; otherwise they are skipped. To run them against the
shared local MongoDB (`~/infra/mongodb`):

```bash
source scripts/test-env.sh
pytest tests/core/db/nosql
```

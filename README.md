# Python FastAPI Template

This project is a microservice application template based on FastAPI. It includes SQLAlchemy (Async), Pydantic, and a
Repository pattern with DDD elements.

## Key Features

- **FastAPI**: Modern, fast Python web framework.
- **Asynchronous SQLAlchemy**: Asynchronous DB engine and session management (supports Master/Slave routing).
- **Repository Pattern**: Decouples data access layer to maintain business logic purity.
- **Environment-based Configuration**: Separated local, dev, and prod environments using `pydantic-settings`.
- **Middleware & Exception Handling**: Includes custom logging, response logs, and common exception handlers.

## Project Structure

```text
.
├── api/                # API routers and versioning
├── app/
│   └── core/           # Common modules (DB, Config, Exception, Middleware, etc.)
├── main.py             # Application entry point
└── tests/              # Test cases
```

## Getting Started

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run Application

Run via `main.py` and specify the environment using the `--env` option (default: `local`).

```bash
python main.py --env local --debug
```

### 3. API Documentation

After running the server, you can access the Swagger documentation at:

- Swagger UI: `http://127.0.0.1:8080/swagger_ui`
- ReDoc: `http://127.0.0.1:8080/redoc`

## Running Tests

```bash
pytest
```

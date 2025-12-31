# Justfile for lahella-automation

# Run all tests (pytest + type checking)
test:
    uv run pytest -v
    uv run ty check

# Run only pytest
pytest:
    uv run pytest -v

# Run type checking
typecheck:
    uv run ty check

# Run linter
lint:
    uv run ruff check

# Run linter with auto-fix
fix:
    uv run ruff check --fix

# Run all checks (lint + test)
check: lint test

# Run tests with coverage report
cov:
    uv run pytest --cov --cov-report=term --cov-report=html
    @echo "HTML report: htmlcov/index.html"

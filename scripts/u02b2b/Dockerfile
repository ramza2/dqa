FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Minimal pinned dependencies for the original Legacy Catalog ORM/finalizer,
# DB integration fixture, python-docx renderer and isolated integration runner.
# Do not install Legacy's full embeddings/torch/LLM development environment.
RUN pip install --no-cache-dir \
    "fastapi==0.115.6" \
    "httpx==0.28.1" \
    "pytest==8.3.4" \
    "SQLAlchemy==2.0.36" \
    "psycopg[binary]==3.2.13" \
    "pgvector==0.3.6" \
    "pydantic-settings==2.7.0" \
    "python-docx==1.1.2" \
    "cryptography==43.0.3"

WORKDIR /legacy/backend
CMD ["python", "-B", "/runner.py"]

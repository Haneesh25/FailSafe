FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    sqlalchemy \
    alembic \
    psycopg2-binary \
    redis \
    rq \
    pydantic \
    pydantic-settings \
    python-multipart \
    jinja2 \
    httpx

# Copy packages
COPY packages/ /app/packages/

# Copy API app
COPY apps/api/ /app/apps/api/

EXPOSE 8000

WORKDIR /app/apps/api

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies including browsers for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    sqlalchemy \
    alembic \
    psycopg2-binary \
    redis \
    rq \
    pydantic \
    pydantic-settings \
    playwright \
    httpx

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy packages
COPY packages/ /app/packages/

# Copy worker app
COPY apps/worker/ /app/apps/worker/

# Set Python path
ENV PYTHONPATH=/app/packages:/app/apps/worker

WORKDIR /app/apps/worker

CMD ["python", "main.py"]

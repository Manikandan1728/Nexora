# --- Stage 1: Builder ---
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies required for psycopg2 and others
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies into the user's local directory
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# --- Stage 2: Runtime ---
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed dependencies
COPY --from=builder /root/.local /root/.local

# Ensure the local bin is on PATH
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Copy application source code
COPY . .

# Create a non-root user and switch to it
RUN useradd -m -s /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose the API port
EXPOSE 8000

# Deterministic healthcheck using Python standard library (no curl required)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

# Start the FastAPI application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

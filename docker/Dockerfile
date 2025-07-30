# Multi-stage Dockerfile for Open Hydro O3

# Build stage
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    make \
    cmake \
    pkg-config \
    libhdf5-dev \
    libatlas-base-dev \
    gfortran \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libhdf5-103 \
    libatlas3-base \
    libgfortran5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create app user
RUN groupadd -r hydro && useradd -r -g hydro hydro

# Create directories
RUN mkdir -p /app /data/hydro/{db,logs,chroma,images} && \
    chown -R hydro:hydro /app /data/hydro

# Copy application code
COPY --chown=hydro:hydro . /app/
WORKDIR /app

# Set environment variables
ENV PYTHONPATH=/app
ENV MOCK_HARDWARE=true
ENV DATABASE_URL=sqlite:////data/hydro/db/hydro.db
ENV CHROMA_PATH=/data/hydro/chroma
ENV LOG_PATH=/data/hydro/logs

# Switch to app user
USER hydro

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Default command
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
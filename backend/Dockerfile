# ============================================================================
# IntegrityShield Backend - GCP Cloud Run Deployment (<$20/month)
# ============================================================================
# Key optimizations:
# - Cloud SQL Proxy sidecar (no VPC connector needed, saves $15-25/month)
# - Multi-stage build for smaller image size
# - Optimized for Cloud Run scale-to-zero
# ============================================================================

# ============================================================================
# Stage 1: Builder - Install Python dependencies
# ============================================================================
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data /app/logs /cloudsql && \
    chown -R appuser:appuser /app /cloudsql

WORKDIR /app

# Install runtime dependencies + Cloud SQL Proxy
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ca-certificates \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Download Cloud SQL Proxy (for connecting to Cloud SQL without VPC connector)
RUN curl -o /usr/local/bin/cloud-sql-proxy \
    https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.11.0/cloud-sql-proxy.linux.amd64 \
    && chmod +x /usr/local/bin/cloud-sql-proxy

# Copy Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . .

# Environment variables
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8080/api/developer/system/health || exit 1

# Startup script that runs both Cloud SQL Proxy and Gunicorn
# Cloud SQL Proxy connects to database via public IP (no VPC connector needed)
CMD /usr/local/bin/cloud-sql-proxy --port 5432 ${CLOUD_SQL_CONNECTION_NAME} & \
    exec gunicorn run:app \
    --bind 0.0.0.0:$PORT \
    --workers 2 \
    --threads 4 \
    --worker-class gthread \
    --worker-tmp-dir /dev/shm \
    --timeout 300 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile - \
    --log-level info

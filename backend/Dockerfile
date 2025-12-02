# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data/pipeline_runs logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=run.py

# Expose port (Cloud Run will set PORT env var)
EXPOSE 8080

# Run database migrations and start app
CMD python -m flask db upgrade && \
    gunicorn run:app \
    --workers 2 \
    --threads 4 \
    --timeout 300 \
    --bind 0.0.0.0:${PORT:-8080} \
    --access-logfile - \
    --error-logfile - \
    --log-level info

# ==============================================================================
# VDSTREAM Dockerfile
# Production-ready container image for VDSTREAM Video Transcoding & Streaming Server
# ==============================================================================

FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies: FFmpeg, FFprobe, and utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Core environment configuration
# Fixed FFmpeg / FFprobe binary paths inside the Linux container
ENV FFMPEG_PATH=/usr/bin/ffmpeg \
    FFPROBE_PATH=/usr/bin/ffprobe

# Base Path prefix for Dashboard and API
ENV DEFAULT_PREFIX=/vdstream

# Persistent storage & Database paths
ENV STORAGE_DIR=/app/storage \
    DOWNLOAD_DIR=/app/downloads \
    DB_URL=sqlite:////app/storage/vdstream.db

# Server binding & Operational settings
ENV HOST=0.0.0.0 \
    PORT=5000 \
    DEBUG=False \
    MAX_CONCURRENT_TRANSCODE=3 \
    MAX_CONCURRENT_STREAMS=10 \
    STREAM_SESSION_TIMEOUT_SECONDS=60 \
    ALLOW_PREVIEW_FALLBACK=True \
    MAX_OUTPUT_VIDEO_SIZE_MB=100 \
    MAX_VIDEO_DURATION_SECONDS=600 \
    RETENTION_DAYS=365

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . /app

# Ensure storage directories exist
RUN mkdir -p /app/storage /app/downloads

# Expose server port 5000
EXPOSE 5000

# Persistent Volumes for Database and Transcoded Video Storage
VOLUME ["/app/storage", "/app/downloads"]

# Container Healthcheck (Supports dynamic prefix for Docker container healthcheck)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=5s \
    CMD python -c "import os, requests; prefix = os.getenv('DEFAULT_PREFIX', ''); requests.get(f'http://localhost:5000{prefix}/api/status')"

# Run the FastAPI server using Uvicorn on port 5000
# (Alternative for Gunicorn: CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "-k", "uvicorn.workers.UvicornWorker", "--log-level", "debug", "--access-logfile", "-", "--error-logfile", "-", "--capture-output", "main:app"])
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]

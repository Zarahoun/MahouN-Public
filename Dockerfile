# ============================================================================
# MAHOUN Backend - Enterprise-Grade Multi-Stage Dockerfile
# ============================================================================
# Architecture: Multi-stage build with security hardening
# Base Image: Python 3.12.7 (Debian Bookworm)
# Build Time: ~5-8 minutes (first build), ~30s (cached)
# Image Size: ~1.2GB (optimized from ~2.5GB)
# ============================================================================
# Build Arguments:
#   - BUILD_ENV: dev|staging|production (default: production)
#   - ENABLE_GPU: true|false (default: false)
#   - PYTHON_VERSION: 3.12.7 (default)
# ============================================================================

ARG PYTHON_VERSION=3.12.7
ARG BUILD_ENV=production

# ============================================================================
# Stage 1: Base - Common dependencies for all stages
# ============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS base

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

# Install system dependencies (minimal, security-focused)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Essential runtime libraries
    ca-certificates \
    curl \
    wget \
    # Database client libraries
    libpq5 \
    # SSL/TLS support
    libssl3 \
    # Compression libraries
    zlib1g \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get autoremove -y

# ============================================================================
# Stage 2: Builder - Compile and install Python dependencies
# ============================================================================
FROM base AS builder

ARG BUILD_ENV

WORKDIR /build

# Install build-time dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Compilers
    gcc \
    g++ \
    make \
    # Development headers
    libpq-dev \
    libssl-dev \
    libffi-dev \
    python3-dev \
    # Build tools
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files ONLY (maximize Docker layer caching)
COPY requirements.txt pyproject.toml README.md ./

# Upgrade pip and install build tools
RUN pip install --no-cache-dir --user --upgrade \
    pip==24.3.1 \
    setuptools==75.6.0 \
    wheel==0.45.1

# If ENABLE_GPU is true, strip the +cpu postfix from requirements to fetch default (CUDA) wheels from PyPI
RUN if [ "$ENABLE_GPU" = "true" ]; then \
        echo "Building with GPU support..."; \
        sed -i 's/+cpu//g' requirements.txt; \
        pip install --no-cache-dir --user -r requirements.txt; \
    else \
        echo "Building for CPU only..."; \
        pip install --no-cache-dir --user -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu; \
    fi

# Install the package itself (if needed for imports)
COPY mahoun/ ./mahoun/
COPY api/ ./api/
RUN pip install --no-cache-dir --user -e .

# ============================================================================
# Stage 3: Development - With dev tools and hot-reload
# ============================================================================
FROM base AS development

ARG BUILD_ENV=dev

WORKDIR /app

# Install development tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Development tools
    git \
    vim \
    less \
    # Debugging tools
    strace \
    gdb \
    # Network tools
    netcat-openbsd \
    iputils-ping \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Add to PATH
ENV PATH=/root/.local/bin:$PATH

# Copy application code (will be mounted as volume in dev)
COPY api/ ./api/
COPY mahoun/ ./mahoun/
COPY config/ ./config/
COPY pyproject.toml README.md ./

# Create runtime directories
RUN mkdir -p \
    /app/data \
    /app/data/dlq \
    /app/uploads \
    /app/vector_store_data \
    /app/output \
    /app/runtime/traces \
    /app/runtime/profiler

# Development runs as root for easier debugging
USER root

EXPOSE 8000

# Development server with hot-reload
CMD ["uvicorn", "api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--reload", \
     "--reload-dir", "/app/api", \
     "--reload-dir", "/app/mahoun", \
     "--log-level", "debug"]

# ============================================================================
# Stage 4: Production - Minimal, hardened, non-root
# ============================================================================
FROM base AS production

ARG BUILD_ENV=production

WORKDIR /app

# Security: Create non-root user with specific UID/GID
# UID 1000 is standard for first user, ensures consistency across environments
RUN groupadd -g 1000 mahoun && \
    useradd -m -u 1000 -g mahoun -s /bin/bash mahoun && \
    # Lock the user account (no password login)
    passwd -l mahoun

# Copy Python packages from builder (with correct ownership)
COPY --from=builder --chown=mahoun:mahoun /root/.local /home/mahoun/.local

# Add user binaries to PATH
ENV PATH=/home/mahoun/.local/bin:$PATH

# Copy application code (with correct ownership)
COPY --chown=mahoun:mahoun api/ ./api/
COPY --chown=mahoun:mahoun mahoun/ ./mahoun/
COPY --chown=mahoun:mahoun config/ ./config/
COPY --chown=mahoun:mahoun pyproject.toml README.md ./

# Create runtime directories with correct permissions
RUN mkdir -p \
    /app/data \
    /app/data/dlq \
    /app/uploads \
    /app/vector_store_data \
    /app/output \
    /app/runtime/traces \
    /app/runtime/profiler \
    /app/logs \
    && chown -R mahoun:mahoun /app \
    && chmod -R 755 /app \
    # Restrict sensitive directories
    && chmod 700 /app/data \
    && chmod 700 /app/uploads

# Security: Switch to non-root user
USER mahoun

# Expose application port
EXPOSE 8000

# Health check with proper timeout and retries
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/system/health || exit 1

# Production-optimized uvicorn with proper signal handling
CMD ["uvicorn", "api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--log-level", "info", \
     "--no-access-log", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]

# ============================================================================
# Stage 5: Testing - With test dependencies
# ============================================================================
FROM development AS testing

# Install test dependencies
RUN pip install --no-cache-dir \
    pytest==8.3.4 \
    pytest-asyncio==0.24.0 \
    pytest-cov==6.0.0 \
    pytest-timeout==2.3.1 \
    pytest-xdist==3.6.1 \
    httpx==0.28.1

# Copy test files and CI scripts
COPY tests/ ./tests/
COPY ci/ ./ci/

# Note: pytest configuration is in pyproject.toml (already copied in development stage)

# Run CI checks followed by tests by default
CMD ["sh", "-c", "python3 ci/scripts/scan_forbidden_patterns.py && python3 ci/scripts/architecture_compliance.py && pytest tests/ -v --tb=short"]

# ============================================================================
# Default stage selection
# ============================================================================
FROM ${BUILD_ENV} AS final


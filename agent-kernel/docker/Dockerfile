# Agent Kernel - Multi-stage Dockerfile
# Combines Gateway (Node.js/NestJS) and Python Kernel (FastAPI)

# ==========================================
# Stage 1: Build Gateway (TypeScript)
# ==========================================
FROM node:18-alpine AS gateway-builder

WORKDIR /build/gateway

# Copy package files for better layer caching
COPY apps/gateway/package*.json ./
COPY packages/shared-schema/package*.json ../packages/shared-schema/
COPY packages/skill-protocol/package*.json ../packages/skill-protocol/
COPY packages/observability/package*.json ../packages/observability/
COPY skills/local/*/package*.json ../skills/local/

# Install dependencies
RUN npm ci --only=production

# Copy source code
COPY apps/gateway/ ./
COPY packages/ ../packages/
COPY skills/ ../skills/

# Build the application
RUN npm run build

# ==========================================
# Stage 2: Python Dependencies
# ==========================================
FROM python:3.11-slim AS python-deps

WORKDIR /build/python

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy Python package files
COPY apps/python-kernel/pyproject.toml ./
COPY apps/python-kernel/main.py ./
COPY apps/python-kernel/*.py ./

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e "."

# ==========================================
# Stage 3: Final Runtime Image
# ==========================================
FROM node:18-alpine AS runtime

# Install Python 3.11 and supervisord
RUN apk add --no-cache \
    python3=~3.11 \
    py3-pip \
    supervisor \
    tzdata \
    curl \
    && ln -sf python3 /usr/bin/python

# Install Python packages system-wide
COPY --from=python-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create application directories
RUN mkdir -p /app/gateway /app/python-kernel /app/data /var/log/supervisor /var/run

# Copy Gateway build artifacts
COPY --from=gateway-builder /build/gateway/dist /app/gateway/dist
COPY --from=gateway-builder /build/gateway/node_modules /app/gateway/node_modules
COPY --from=gateway-builder /build/gateway/package*.json /app/gateway/

# Copy Python Kernel source
COPY apps/python-kernel/ /app/python-kernel/

# Copy local packages that Python Kernel depends on
COPY packages/ /app/packages/

# Copy supervisord configuration
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create non-root user
RUN addgroup -g 1000 agentkernel && \
    adduser -u 1000 -G agentkernel -s /bin/sh -D agentkernel && \
    chown -R agentkernel:agentkernel /app /var/log/supervisor /var/run

# Set working directory
WORKDIR /app

# Environment variables
ENV NODE_ENV=production
ENV PORT=3000
ENV PYTHON_KERNEL_PORT=8000
ENV DATA_PATH=/app/data
ENV GATEWAY_STORAGE_PATH=/app/data/gateway
ENV LOG_LEVEL=INFO
ENV TZ=UTC

# Expose ports
EXPOSE 3000 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Switch to non-root user
USER agentkernel

# Start supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

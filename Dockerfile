# ------------- Builder Stage -------------
FROM ghcr.io/astral-sh/uv:python3.13-bookworm AS builder

WORKDIR /app

# Copy dependency files do NOT try to install the project (sources aren’t here yet)
COPY pyproject.toml uv.lock ./

# Install dependencies (locked, reproducible)
RUN uv sync --frozen --no-dev

# ------------- Runtime Stage -------------
FROM python:3.13-slim AS runtime

# Security: Install only runtime security updates
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends tini \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* /var/tmp/*

# Runtime environment configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CONTEXT=/ \
    PORT=8080 \
    HOME=/tmp \
    XDG_DATA_HOME=/tmp/.local/share \
    XDG_CACHE_HOME=/tmp/.cache \
    XDG_CONFIG_HOME=/tmp/.config


# Security: Create restricted non-root user with minimal permissions
RUN groupadd --system --gid 1001 calibo \
    && useradd --system --uid 1001 --gid calibo \
    --home-dir /app --no-create-home \
    --shell /usr/sbin/nologin calibo

# Set working directory with proper permissions
WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Ensure venv is executable
RUN chmod -R 755 /app/.venv

# Make sure to use venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY --chown=calibo:calibo src ./src
COPY --chown=calibo:calibo knowledge ./knowledge

# Create actual writable runtime directories
RUN mkdir -p /tmp/.local/share /tmp/.cache /tmp/.config \
    && chown -R calibo:calibo /tmp

RUN chmod 755 /app \
    && chmod 1777 /tmp \
    && chmod -R 755 /app/src \
    && chmod -R 755 /app/knowledge \
    && chmod -R 755 /app/.venv \
    && mkdir -p /app/data \
    && chown -R calibo:calibo /app/data \ 
    && chmod -R 750 /app/data \
    && find /app/src -name "*.py" -exec chmod 644 {} \;

# Security: Clean up
RUN apt-get autoremove -y \
    && apt-get autoclean \
    && rm -rf /var/cache/apt/* \
    && rm -rf /usr/share/doc/* \
    && rm -rf /usr/share/man/* \
    && rm -rf /var/tmp/*

# Switch to non-root user
USER calibo

# Security: Use dumb-init to handle signals properly and gunicorn security settings
ENTRYPOINT ["tini", "--"]

# Default command with security considerations 
CMD ["python", "-m", "latest_ai_development.main"]

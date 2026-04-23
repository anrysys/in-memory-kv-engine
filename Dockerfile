# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    LOG_LEVEL=INFO \
    HOST=0.0.0.0 \
    PORT=9888

WORKDIR /app

# Create a non-root user.
RUN groupadd --system ember && useradd --system --gid ember --home /app ember

# Install the package. Copy metadata first so layer caching works.
COPY pyproject.toml README.md ./
COPY ember_cache ./ember_cache
RUN pip install --no-cache-dir .

USER ember
EXPOSE 9888

# A simple PING-based healthcheck. Exits 0 when the server replies "Ok".
HEALTHCHECK --interval=10s --timeout=3s --start-period=3s --retries=3 \
    CMD python -c "import socket,sys; \
s=socket.create_connection(('127.0.0.1',9888),2); \
s.sendall(b'PING\n'); \
data=s.recv(128); s.close(); \
sys.exit(0 if b'\"Ok\"' in data else 1)"

CMD ["python", "-m", "ember_cache"]

# Docker image for the Hartford County simulation backend (Alternative #4).
#
# Build:  docker build -t hartford-grid-server .
# Run:    docker run -p 8000:8000 hartford-grid-server
#
# For deployment to Render / Fly.io / Railway, push this image or let the
# platform build it from this Dockerfile.

FROM python:3.11-slim

WORKDIR /app

# Install only the runtime deps the server needs (skip geopandas — it has
# heavy native deps and the server doesn't use it).
RUN pip install --no-cache-dir \
        "fastapi>=0.110" \
        "uvicorn[standard]>=0.27" \
        "pydantic>=2.5" \
        "numpy>=1.26" \
        "scipy>=1.11" \
        "numba>=0.59"
# matplotlib is intentionally NOT installed: it's only used by
# 05_generate_artifacts.py for offline plotting, and the server now
# wraps that import in try/except so the file is optional. Saving the
# matplotlib install keeps us well under Render's free-tier 512MB RAM.

# Copy the server, the reference scheduler, and the fast/JIT'd schedulers.
COPY 07_server.py scheduler_fast.py scheduler_numba.py ./

EXPOSE 8000

# Hosts like Render set $PORT; fall back to 8000 locally.
CMD ["sh", "-c", "uvicorn 07_server:app --host 0.0.0.0 --port ${PORT:-8000}"]

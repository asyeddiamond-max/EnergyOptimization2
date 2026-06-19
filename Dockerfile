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

# Copy the server, the reference scheduler, and the fast/JIT'd schedulers.
COPY 07_server.py 05_generate_artifacts.py scheduler_fast.py scheduler_numba.py ./

EXPOSE 8000

# Hosts like Render set $PORT; fall back to 8000 locally.
CMD ["sh", "-c", "uvicorn 07_server:app --host 0.0.0.0 --port ${PORT:-8000}"]

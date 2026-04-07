# ─── Stage 1: Build Next.js ────────────────────────────────────────────────────
# Produces a self-contained .next/standalone output that runs without the
# full node_modules tree — keeps the final image lean.
FROM node:20-slim AS node-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./

# NEXT_PUBLIC_ vars are inlined at build time.
# Default to /api so the browser calls the nginx proxy on the same origin.
# Override at build time with:  docker build --build-arg NEXT_PUBLIC_API_BASE_URL=...
ARG NEXT_PUBLIC_API_BASE_URL=/api
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

RUN npm run build


# ─── Stage 2: Python dependencies ──────────────────────────────────────────────
# Install into a venv so we can COPY just the venv to the final stage
# without pulling in the full python build toolchain.
FROM python:3.12-slim AS python-deps

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt ./
# Exclude faiss-cpu and fastembed — both ship AVX2-optimised native code that
# crashes on Cloud Run CPUs that don't expose AVX2 (SIGILL before Python starts).
# The retriever falls back to KeywordRetriever automatically when faiss is absent.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && grep -vE "^faiss-cpu|^fastembed" requirements.txt > requirements-docker.txt \
    && pip install --no-cache-dir -r requirements-docker.txt \
    && apt-get purge -y build-essential && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*


# ─── Stage 3: Runtime image ────────────────────────────────────────────────────
# Python 3.12 as base — must match the python-deps stage so the copied venv's
# interpreter symlinks resolve correctly.  Node.js 20 is installed on top.
FROM python:3.12-slim AS runtime

# Install Node.js 20 (via NodeSource), nginx, supervisor
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs nginx supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python venv (from python-deps stage — same Python 3.12 base) ─────────────
COPY --from=python-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# ── FastAPI backend ───────────────────────────────────────────────────────────
COPY backend/app ./backend/app

# ── Next.js standalone build ──────────────────────────────────────────────────
# The standalone directory contains a minimal server.js + node_modules subset.
COPY --from=node-builder /app/frontend/.next/standalone ./frontend/
# Static assets must be copied alongside the server manually (Next.js convention).
COPY --from=node-builder /app/frontend/.next/static ./frontend/.next/static/
COPY --from=node-builder /app/frontend/public ./frontend/public/

# ── nginx & supervisor config ─────────────────────────────────────────────────
COPY deploy/nginx.conf       /etc/nginx/nginx.conf
# Replace the default supervisord.conf entirely so there are no section conflicts.
COPY deploy/supervisord.conf /etc/supervisord.conf

# Cloud Run expects the container to listen on 8080
EXPOSE 8080

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisord.conf"]

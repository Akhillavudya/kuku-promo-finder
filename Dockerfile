# One container: the built React app and the API that serves it, on one URL.
#
# Two stages so node never reaches the runtime image - the frontend is static
# files by the time Python sees it. `pack/` and `brief/` are excluded by
# .dockerignore and must never appear here (D8, hard rule 5).

# --- stage 1: build the React app ---------------------------------------
FROM node:22-alpine AS web

WORKDIR /build
# package.json first, so a source-only change does not reinstall 68 packages.
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY web/ ./
RUN npm run build


# --- stage 2: the runtime ------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# The pipeline, its config, the API, and the synthetic sample episode.
COPY src/ ./src/
COPY config/ ./config/
COPY api/ ./api/
COPY examples/ ./examples/

# Precomputed output: this is what the Season tab serves, and it is the
# reason that tab needs no key and makes no model call. Quotes the hook and
# cliffhanger lines only (D8).
COPY outputs/ ./outputs/

# The built frontend, from stage 1.
COPY --from=web /build/dist ./web/dist

# Hosts inject $PORT; 7860 is the default both Render and HF Spaces accept.
ENV PORT=7860
EXPOSE 7860

# Shell form, so ${PORT} is expanded by the shell rather than passed literally.
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-7860}

FROM node:20-alpine AS frontend
WORKDIR /build
COPY inventory-frontend/package*.json ./
RUN npm ci
COPY inventory-frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade "pip>=26.1.2" \
    && pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y pip \
    && rm -rf /root/.cache/pip

COPY . .
COPY --from=frontend --chown=appuser:appuser /build/dist inventory-frontend/dist

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8002/health || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port 8002"]

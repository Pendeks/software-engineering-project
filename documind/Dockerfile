FROM node:22-alpine AS frontend-build

WORKDIR /frontend
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOCUMIND_WEB_STATIC_PATH=/app/web-dist \
    DOCUMIND_STORAGE_PATH=/var/lib/documind/uploads

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

COPY --from=frontend-build /frontend/dist /app/web-dist

RUN groupadd --system documind \
    && useradd --system --gid documind --home-dir /app --no-create-home --shell /usr/sbin/nologin documind \
    && mkdir -p /var/lib/documind/uploads \
    && chown -R documind:documind /var/lib/documind

USER documind

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2)"]

ENTRYPOINT ["uvicorn", "documind.main:app", "--host", "0.0.0.0", "--port", "8000"]

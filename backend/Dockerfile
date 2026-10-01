# Build context is the repository ROOT (see docker-compose.yml) so the shared
# packages/ can be COPY'd in. Keep .dockerignore excluding node_modules/.venv/etc.
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Shared packages (importable as app_logger / app_metrics via PYTHONPATH=/app).
COPY packages/app_logger /app/app_logger
COPY packages/app_metrics /app/app_metrics

# Application code + migrations + entrypoint.
COPY backend/app /app/app
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini
COPY backend/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Identity source of truth — also readable in-container (config falls back to env).
COPY app.config.json /app/app.config.json

ENV PYTHONPATH=/app
ENV APP_CONFIG_PATH=/app/app.config.json

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

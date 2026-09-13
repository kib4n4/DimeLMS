FROM python:3.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# System deps:
# - build-essential/libpq-dev -> psycopg2 (Postgres)
# - gettext                   -> compilemessages (this project ships es/fr/ru locales)
# - curl                      -> container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        gettext \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ ./requirements/
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements/production.txt

COPY . .

RUN chmod +x docker/entrypoint.sh

RUN mkdir -p /app/staticfiles /app/media

EXPOSE 8000

ENTRYPOINT ["docker/entrypoint.sh"]
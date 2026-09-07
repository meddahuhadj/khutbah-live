# Déploiement sur hôte persistant (Railway / Fly.io / Render / VPS)
# Une seule instance = processus long : WebSockets + rooms en mémoire.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dépendances d'abord (couche de cache efficace lors des rebuilds)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY SYSTEM_PROMPT.md .

# Config locale éventuelle servie par la plateforme (nejamais committer .env)
ENV TZ=UTC

WORKDIR /app/backend

# Main lit le port via la variable PORT fournie par la plateforme
EXPOSE 8000
CMD ["python", "main.py"]
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dépendances d'abord : cette couche est mise en cache tant que requirements.txt ne change pas.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Code et schéma SQL (les identifiants ne sont JAMAIS copiés dans l'image :
# ils arrivent par variables d'environnement au lancement du conteneur).
COPY src ./src
COPY sql ./sql

RUN useradd --create-home --uid 1000 app
USER app

# Un conteneur = une exécution de la pipeline (lancée régulièrement par le CD).
CMD ["python", "-m", "src.pipeline"]

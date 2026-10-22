#!/bin/sh
# Lance une exécution de la pipeline (appelé par cron toutes les 5 minutes).
# - `flock -n` : si l'exécution précédente tourne encore, celle-ci est ignorée.
# - code de sortie propagé : une erreur de la pipeline est visible dans les logs cron.
set -eu

cd "$(dirname "$0")"

exec flock -n /tmp/transactions-pipeline.lock \
  docker compose --profile job run --rm -T app

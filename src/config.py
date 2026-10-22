"""Configuration par variables d'environnement (jamais de secret dans le dépôt).

En local les valeurs viennent du fichier `.env` (ignoré par git) ; en CI, des
secrets et variables GitHub. Une variable déjà définie n'est pas écrasée.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]


class MissingConfigError(RuntimeError):
    """Une variable d'environnement obligatoire n'est pas définie."""


def load_env() -> None:
    load_dotenv(ROOT_DIR / ".env", override=False)


def required_env(name: str) -> str:
    load_env()
    value = os.environ.get(name)
    if not value:
        raise MissingConfigError(
            f"Variable d'environnement {name} manquante "
            "(à définir dans le fichier .env en local, "
            "ou dans les secrets/variables GitHub en CI)."
        )
    return value

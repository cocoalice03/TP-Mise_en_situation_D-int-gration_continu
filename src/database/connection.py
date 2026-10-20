import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from pymysql.connections import Connection

ROOT_DIR = Path(__file__).resolve().parents[2]
DDL_DIR = ROOT_DIR / "sql" / "ddl"


class MissingConfigError(RuntimeError):
    """Une variable d'environnement obligatoire n'est pas définie."""


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingConfigError(
            f"Variable d'environnement {name} manquante "
            "(à définir dans le fichier .env en local, ou dans les secrets/variables GitHub en CI)."
        )
    return value


def get_connection() -> Connection:
    """Ouvre une connexion MySQL depuis les variables d'environnement.

    Les identifiants (MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE) n'ont pas de
    valeur par défaut : ils ne doivent jamais être écrits dans le dépôt.
    En local ils viennent du fichier `.env` (ignoré par git) ; en CI, des
    secrets/variables GitHub. Une variable déjà définie n'est pas écrasée.
    """
    load_dotenv(ROOT_DIR / ".env", override=False)
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=_required_env("MYSQL_USER"),
        password=_required_env("MYSQL_PASSWORD"),
        database=_required_env("MYSQL_DATABASE"),
        charset="utf8mb4",
        autocommit=False,
    )


def init_db(conn: Connection) -> None:
    """Exécute les fichiers DDL (sql/ddl/*.sql, dans l'ordre alphabétique)."""
    with conn.cursor() as cursor:
        for ddl_file in sorted(DDL_DIR.glob("*.sql")):
            cursor.execute(ddl_file.read_text(encoding="utf-8"))
    conn.commit()

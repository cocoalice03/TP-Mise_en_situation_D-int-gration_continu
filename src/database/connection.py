import os

import pymysql
from pymysql.connections import Connection

from src.config import ROOT_DIR, MissingConfigError, load_env, required_env

__all__ = ["ROOT_DIR", "DDL_DIR", "MissingConfigError", "get_connection", "init_db"]

DDL_DIR = ROOT_DIR / "sql" / "ddl"


def get_connection() -> Connection:
    """Ouvre une connexion MySQL depuis les variables d'environnement.

    Les identifiants (MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE) n'ont pas de
    valeur par défaut : ils ne doivent jamais être écrits dans le dépôt.
    En local ils viennent du fichier `.env` (ignoré par git) ; en CI, des
    secrets/variables GitHub. Une variable déjà définie n'est pas écrasée.
    """
    load_env()
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=required_env("MYSQL_USER"),
        password=required_env("MYSQL_PASSWORD"),
        database=required_env("MYSQL_DATABASE"),
        charset="utf8mb4",
        autocommit=False,
    )


def init_db(conn: Connection) -> None:
    """Exécute les fichiers DDL (sql/ddl/*.sql, dans l'ordre alphabétique)."""
    with conn.cursor() as cursor:
        for ddl_file in sorted(DDL_DIR.glob("*.sql")):
            cursor.execute(ddl_file.read_text(encoding="utf-8"))
    conn.commit()

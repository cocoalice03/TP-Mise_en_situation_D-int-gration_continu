import os
from pathlib import Path

import pymysql
from pymysql.connections import Connection

DDL_DIR = Path(__file__).resolve().parents[2] / "sql" / "ddl"


def get_connection() -> Connection:
    """Ouvre une connexion MySQL depuis les variables d'environnement."""
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "app"),
        password=os.environ.get("MYSQL_PASSWORD", "app_password"),
        database=os.environ.get("MYSQL_DATABASE", "transactions"),
        charset="utf8mb4",
        autocommit=False,
    )


def init_db(conn: Connection) -> None:
    """Exécute les fichiers DDL (sql/ddl/*.sql, dans l'ordre alphabétique)."""
    with conn.cursor() as cursor:
        for ddl_file in sorted(DDL_DIR.glob("*.sql")):
            cursor.execute(ddl_file.read_text(encoding="utf-8"))
    conn.commit()

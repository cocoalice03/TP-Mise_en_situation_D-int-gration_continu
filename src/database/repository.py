from collections.abc import Callable
from datetime import datetime
from typing import Any

import pymysql
from pymysql.connections import Connection

from src.database.connection import get_connection
from src.database.retry_policy import (
    DB_RETRY_ON,
    DUPLICATE_ENTRY_CODE,
    is_retryable_db_error,
)
from src.retry import call_with_retry

SELECT_PROCESSED_FILE = "SELECT 1 FROM processed_files WHERE file_hash = %s"

INSERT_TRANSACTION = """
    INSERT INTO transactions (
        datetime_transaction, iban_origine, pays_source, banque_source,
        iban_destinataire, pays_destinataire, montant, is_high_value
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""

INSERT_PROCESSED_FILE = """
    INSERT INTO processed_files (filename, file_hash, rows_count)
    VALUES (%s, %s, %s)
"""


def is_file_processed(conn: Connection, file_hash: str) -> bool:
    """Indique si un fichier (identifié par son hash) a déjà été traité."""
    with conn.cursor() as cursor:
        cursor.execute(SELECT_PROCESSED_FILE, (file_hash,))
        found = cursor.fetchone() is not None
    conn.commit()  # termine la transaction de lecture
    return found


def insert_transactions(
    conn: Connection,
    transactions: list[dict[str, Any]],
    filename: str,
    file_hash: str,
) -> int:
    """Insère les transactions traitées d'un fichier et le marque comme traité.

    Attend la sortie de `flag_high_value_transactions`. Les transactions et la
    ligne `processed_files` sont écrites dans la même transaction SQL : en cas
    d'erreur, rollback et rien n'est écrit. Un fichier ne peut pas être inséré
    deux fois (contrainte d'unicité sur le hash). Retourne le nombre de lignes
    insérées.
    """
    # Préparation avant d'ouvrir la transaction : une donnée invalide échoue ici
    rows = [
        (
            datetime.strptime(t["datetime_transaction"], "%Y-%m-%d %H:%M:%S"),
            t["iban_origine"],
            t["pays_source"],
            t["banque_source"],
            t["iban_destinataire"],
            t["pays_destinataire"],
            t["montant"],
            bool(t["is_high_value"]),
        )
        for t in transactions
    ]
    try:
        with conn.cursor() as cursor:
            cursor.executemany(INSERT_TRANSACTION, rows)
            cursor.execute(INSERT_PROCESSED_FILE, (filename, file_hash, len(rows)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows)


def insert_transactions_with_retry(
    transactions: list[dict[str, Any]],
    filename: str,
    file_hash: str,
    connect: Callable[[], Connection] | None = None,
) -> int | None:
    """`insert_transactions` avec retry, sans jamais créer de doublon.

    Chaque tentative utilise une connexion neuve. Après un échec, la tentative
    suivante vérifie d'abord si le fichier est déjà enregistré : le cas où le
    commit a réussi mais où la réponse s'est perdue ne réinsère donc rien.
    Un doublon de hash (IntegrityError 1062) signifie "déjà traité" : ce n'est
    ni retenté ni remonté comme erreur. Retourne None dans ce cas.
    """
    open_connection = connect or get_connection
    failed_before = False

    def attempt() -> int | None:
        nonlocal failed_before
        try:
            conn = open_connection()
            try:
                if failed_before and is_file_processed(conn, file_hash):
                    return len(transactions)
                return insert_transactions(conn, transactions, filename, file_hash)
            finally:
                conn.close()
        except pymysql.err.IntegrityError as error:
            if error.args and error.args[0] == DUPLICATE_ENTRY_CODE:
                return None
            raise
        except Exception:
            failed_before = True
            raise

    return call_with_retry(
        attempt,
        operation=f"insertion MySQL de {filename}",
        retry_on=DB_RETRY_ON,
        is_retryable=is_retryable_db_error,
    )

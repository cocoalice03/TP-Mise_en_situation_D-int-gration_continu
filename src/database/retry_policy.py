"""Quelles erreurs MySQL valent la peine d'être retentées (spec §4.8)."""
import pymysql

DB_RETRY_ON: tuple[type[Exception], ...] = (
    pymysql.err.OperationalError,
    pymysql.err.InterfaceError,
)

# Erreurs transitoires : serveur injoignable / connexion perdue (2003, 2006,
# 2013), trop de connexions (1040), verrou ou deadlock (1205, 1213).
# Les autres OperationalError (accès refusé 1045, base inconnue 1049...) sont
# permanentes : inutile de réessayer.
TRANSIENT_MYSQL_CODES = {1040, 1205, 1213, 2003, 2006, 2013}

DUPLICATE_ENTRY_CODE = 1062


def is_retryable_db_error(error: Exception) -> bool:
    if isinstance(error, pymysql.err.InterfaceError):
        return True
    code = error.args[0] if error.args and isinstance(error.args[0], int) else None
    return code in TRANSIENT_MYSQL_CODES

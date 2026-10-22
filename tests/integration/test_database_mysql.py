"""Couche base de données contre un vrai MySQL (docker compose up -d --wait)."""
import pymysql
import pytest
from pymysql.connections import Connection

from src.database import insert_transactions, is_file_processed
from src.processing import flag_high_value_transactions
from tests.integration.conftest import fetch_all


RAW = [
    {
        "datetime_transaction": "2026-10-01 10:01:00",
        "iban_origine": "FR7600000000000000000001",
        "pays_source": "FR",
        "banque_source": "BNP Paribas",
        "iban_destinataire": "DE7600000000000000000002",
        "pays_destinataire": "DE",
        "montant": "15000.00",
    },
]


def _count(conn: Connection, table: str) -> int:
    return int(fetch_all(conn, f"SELECT COUNT(*) FROM {table}")[0][0])


def test_insert_and_track_file(conn: Connection) -> None:
    assert not is_file_processed(conn, "h1")
    insert_transactions(conn, flag_high_value_transactions(RAW), "a.csv", "h1")
    assert is_file_processed(conn, "h1")
    assert _count(conn, "transactions") == 1


def test_same_file_twice_is_rejected_and_rolled_back(conn: Connection) -> None:
    flagged = flag_high_value_transactions(RAW)
    insert_transactions(conn, flagged, "a.csv", "h1")
    with pytest.raises(pymysql.err.IntegrityError):
        insert_transactions(conn, flagged, "a.csv", "h1")
    assert _count(conn, "transactions") == 1

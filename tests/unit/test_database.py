from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.database import init_db, insert_transactions, is_file_processed
from src.database.connection import DDL_DIR
from src.processing import flag_high_value_transactions

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
    {
        "datetime_transaction": "2026-10-01 10:06:00",
        "iban_origine": "FR7600000000000000000001",
        "pays_source": "FR",
        "banque_source": "BNP Paribas",
        "iban_destinataire": "ES7600000000000000000003",
        "pays_destinataire": "ES",
        "montant": "42.50",
    },
]


def _mock_conn() -> tuple[MagicMock, MagicMock]:
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    return conn, cursor


def test_ddl_files_exist() -> None:
    names = [p.name for p in sorted(DDL_DIR.glob("*.sql"))]
    assert names == ["001_processed_files.sql", "002_transactions.sql"]


def test_init_db_executes_each_ddl_file_then_commits() -> None:
    conn, cursor = _mock_conn()
    init_db(conn)
    executed = [c.args[0] for c in cursor.execute.call_args_list]
    assert len(executed) == 2
    assert "processed_files" in executed[0]
    assert "transactions" in executed[1]
    conn.commit.assert_called_once()


def test_insert_transactions_uses_bound_parameters_and_commits() -> None:
    conn, cursor = _mock_conn()
    n = insert_transactions(conn, flag_high_value_transactions(RAW), "a.csv", "h1")
    assert n == 2

    sql, rows = cursor.executemany.call_args.args
    assert "%s" in sql and "15000" not in sql  # jamais de valeur concaténée
    assert rows[0][0] == datetime(2026, 10, 1, 10, 1, 0)
    assert rows[0][-1] is True and rows[1][-1] is False
    assert cursor.execute.call_args.args[1] == ("a.csv", "h1", 2)
    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()


def test_insert_rolls_back_on_database_error() -> None:
    conn, cursor = _mock_conn()
    cursor.execute.side_effect = RuntimeError("duplicate hash")
    with pytest.raises(RuntimeError):
        insert_transactions(conn, flag_high_value_transactions(RAW), "a.csv", "h1")
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_insert_invalid_data_fails_before_any_sql() -> None:
    conn, cursor = _mock_conn()
    bad: list[dict[str, Any]] = [{"montant": 1}]
    with pytest.raises(KeyError):
        insert_transactions(conn, bad, "a.csv", "h1")
    cursor.executemany.assert_not_called()


@pytest.mark.parametrize("row,expected", [((1,), True), (None, False)])
def test_is_file_processed(row: Any, expected: bool) -> None:
    conn, cursor = _mock_conn()
    cursor.fetchone.return_value = row
    assert is_file_processed(conn, "h1") is expected
    assert cursor.execute.call_args.args[1] == ("h1",)

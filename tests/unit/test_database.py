from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pymysql
import pytest

from src.database import (
    init_db,
    insert_transactions,
    insert_transactions_with_retry,
    is_file_processed,
    is_retryable_db_error,
)
from src.database.connection import DDL_DIR
from src.processing import flag_high_value_transactions
from src.retry import RetryExhaustedError

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
    assert names == ["processed_files.sql", "transactions.sql"]


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


# --- Retry de l'insertion (spec 4.8) ---------------------------------------


def _connections(*conns: MagicMock) -> Any:
    """Fabrique `connect()` qui renvoie les connexions données, dans l'ordre."""
    it = iter(conns)
    return lambda: next(it)


def _conn_with(fetchone: Any = None) -> MagicMock:
    conn, cursor = _mock_conn()
    cursor.fetchone.return_value = fetchone
    return conn


def test_retry_insert_succeeds_after_transient_failure() -> None:
    flagged = flag_high_value_transactions(RAW)
    bad = _conn_with()
    bad.cursor.return_value.__enter__.return_value.executemany.side_effect = (
        pymysql.err.OperationalError(2013, "Lost connection")
    )
    good = _conn_with(fetchone=None)  # fichier pas encore enregistré

    n = insert_transactions_with_retry(flagged, "a.csv", "h1", _connections(bad, good))

    assert n == 2
    bad.rollback.assert_called_once()
    good.commit.assert_called()
    bad.close.assert_called_once()
    good.close.assert_called_once()


def test_retry_does_not_reinsert_when_previous_attempt_actually_committed() -> None:
    """Commit réussi mais réponse perdue : la tentative suivante ne réinsère rien."""
    flagged = flag_high_value_transactions(RAW)
    lost_ack = _conn_with()
    lost_ack.commit.side_effect = pymysql.err.OperationalError(2013, "Lost connection")
    second = _conn_with(fetchone=(1,))  # le fichier est déjà enregistré

    n = insert_transactions_with_retry(flagged, "a.csv", "h1", _connections(lost_ack, second))

    assert n == 2
    second.cursor.return_value.__enter__.return_value.executemany.assert_not_called()


def test_retry_insert_exhausted_raises_explicit_error() -> None:
    flagged = flag_high_value_transactions(RAW)

    def connect() -> MagicMock:
        raise pymysql.err.OperationalError(2003, "Can't connect to MySQL server")

    with pytest.raises(RetryExhaustedError, match="insertion MySQL de a.csv"):
        insert_transactions_with_retry(flagged, "a.csv", "h1", connect)


def test_retry_insert_duplicate_hash_means_already_processed() -> None:
    flagged = flag_high_value_transactions(RAW)
    conn = _conn_with()
    conn.cursor.return_value.__enter__.return_value.execute.side_effect = (
        pymysql.err.IntegrityError(1062, "Duplicate entry")
    )
    calls = 0

    def connect() -> MagicMock:
        nonlocal calls
        calls += 1
        return conn

    assert insert_transactions_with_retry(flagged, "a.csv", "h1", connect) is None
    assert calls == 1  # pas de nouvelle tentative


def test_retry_insert_permanent_error_is_not_retried() -> None:
    flagged = flag_high_value_transactions(RAW)
    calls = 0

    def connect() -> MagicMock:
        nonlocal calls
        calls += 1
        raise pymysql.err.OperationalError(1045, "Access denied")

    with pytest.raises(pymysql.err.OperationalError):
        insert_transactions_with_retry(flagged, "a.csv", "h1", connect)
    assert calls == 1


@pytest.mark.parametrize(
    "error,expected",
    [
        (pymysql.err.OperationalError(2003, "x"), True),
        (pymysql.err.OperationalError(2013, "x"), True),
        (pymysql.err.OperationalError(1213, "deadlock"), True),
        (pymysql.err.OperationalError(1205, "lock wait"), True),
        (pymysql.err.InterfaceError(0, "x"), True),
        (pymysql.err.OperationalError(1045, "access denied"), False),
        (pymysql.err.OperationalError(1049, "unknown database"), False),
    ],
)
def test_is_retryable_db_error(error: Exception, expected: bool) -> None:
    assert is_retryable_db_error(error) is expected

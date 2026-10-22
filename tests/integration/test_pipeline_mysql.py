"""Pipeline complète (CSV -> MinIO -> traitement -> MySQL) vérifiée en base."""
import csv
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pymysql.connections import Connection

from src.generator import create_csv_files
from src.generator.data import FIELDNAMES
from src.loader import load_all_csv_from_directory
from src.pipeline import main, run_pipeline
from src.processing import (
    sum_by_banque_source,
    sum_by_iban_destinataire,
    sum_by_iban_origine,
)
from src.storage import get_bucket_name, list_csv_keys, upload_files
from tests.integration.conftest import fetch_all


A, B = "FR7611111111111111111111", "DE7622222222222222222222"
C, X = "ES7633333333333333333333", "FR7644444444444444444444"

# Jeu de données maîtrisé : valeurs attendues calculées à la main.
KNOWN_ROWS = [
    ("2026-10-01 10:01:00", A, "FR", "BNP Paribas", X, "FR", "15000.00"),
    ("2026-10-01 10:06:00", A, "FR", "BNP Paribas", C, "ES", "42.50"),
    ("2026-10-01 10:11:00", B, "DE", "Commerzbank", C, "ES", "5000.00"),  # = seuil
    ("2026-10-01 10:16:00", B, "DE", "Commerzbank", X, "FR", "5000.01"),
]


def _write_known_csv(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "known.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDNAMES)
        w.writerows(KNOWN_ROWS)


def _upload(s3: Any, directory: Path) -> None:
    """Dépose les CSV d'un dossier dans le bucket de test (étape génération -> MinIO)."""
    upload_files(s3, get_bucket_name(), sorted(directory.glob("*.csv")))


def _count(conn: Connection, sql: str) -> int:
    return int(fetch_all(conn, sql)[0][0])


def _sum_sql(conn: Connection, column: str) -> dict[str, Decimal]:
    rows = fetch_all(
        conn, f"SELECT {column}, SUM(montant) FROM transactions GROUP BY {column}"
    )
    return {k: v for k, v in rows}


def test_values_are_stored_correctly(conn: Connection, s3: Any, tmp_path: Path) -> None:
    _write_known_csv(tmp_path)
    _upload(s3, tmp_path)
    run_pipeline(generate=False)

    rows = fetch_all(
        conn,
        "SELECT datetime_transaction, iban_origine, pays_source, banque_source,"
        " iban_destinataire, pays_destinataire, montant FROM transactions"
        " ORDER BY datetime_transaction",
    )
    assert len(rows) == len(KNOWN_ROWS)
    for stored, expected in zip(rows, KNOWN_ROWS):
        assert str(stored[0]) == expected[0]
        assert tuple(stored[1:6]) == expected[1:6]
        assert stored[6] == Decimal(expected[6])


def test_high_value_flags(conn: Connection, s3: Any, tmp_path: Path) -> None:
    _write_known_csv(tmp_path)
    _upload(s3, tmp_path)
    run_pipeline(generate=False)

    flags = fetch_all(
        conn,
        "SELECT montant, is_high_value FROM transactions"
        " ORDER BY datetime_transaction",
    )
    # Le seuil est strict : 5000.00 n'est PAS une transaction à risque.
    assert [(float(m), bool(f)) for m, f in flags] == [
        (15000.00, True),
        (42.50, False),
        (5000.00, False),
        (5000.01, True),
    ]


def test_aggregations_match_expected_results(
    conn: Connection, s3: Any, tmp_path: Path
) -> None:
    _write_known_csv(tmp_path)
    _upload(s3, tmp_path)
    run_pipeline(generate=False)

    expected_origine = {A: Decimal("15042.50"), B: Decimal("10000.01")}
    expected_banque = {
        "BNP Paribas": Decimal("15042.50"),
        "Commerzbank": Decimal("10000.01"),
    }
    expected_dest = {X: Decimal("20000.01"), C: Decimal("5042.50")}

    # Résultats attendus (calculés à la main) = agrégation SQL sur la base
    assert _sum_sql(conn, "iban_origine") == expected_origine
    assert _sum_sql(conn, "banque_source") == expected_banque
    assert _sum_sql(conn, "iban_destinataire") == expected_dest

    # ... = fonctions de traitement appliquées sur le CSV
    data: list[dict[str, Any]] = load_all_csv_from_directory(tmp_path)
    for fn, expected in [
        (sum_by_iban_origine, expected_origine),
        (sum_by_banque_source, expected_banque),
        (sum_by_iban_destinataire, expected_dest),
    ]:
        assert {k: Decimal(str(v)) for k, v in fn(data).items()} == expected


def test_generated_files_are_inserted_except_rejected_rows(
    conn: Connection, s3: Any, tmp_path: Path
) -> None:
    files = create_csv_files(num_files=3, output_dir=tmp_path)
    csv_rows = load_all_csv_from_directory(tmp_path)
    _upload(s3, tmp_path)
    run_pipeline(generate=False)

    # Chaque fichier contient un montant négatif (-50.00) injecté : rejeté par la validation.
    negatives = [r for r in csv_rows if float(r["montant"]) <= 0]
    assert len(negatives) == 3
    assert _count(conn, "SELECT COUNT(*) FROM transactions") == len(csv_rows) - 3

    tracked = fetch_all(
        conn, "SELECT filename, rows_count FROM processed_files ORDER BY filename"
    )
    assert [t[0] for t in tracked] == [f.name for f in sorted(files)]
    assert sum(t[1] for t in tracked) == len(csv_rows) - 3

    # Aucune donnée invalide en base, et le flag est cohérent avec le montant.
    assert _count(conn, "SELECT COUNT(*) FROM transactions WHERE montant <= 0") == 0
    assert _count(
        conn,
        "SELECT COUNT(*) FROM transactions WHERE is_high_value <> (montant > 5000)",
    ) == 0
    assert _count(conn, "SELECT COUNT(*) FROM transactions WHERE is_high_value") >= 1


def test_rerun_does_not_duplicate(conn: Connection, s3: Any, tmp_path: Path) -> None:
    create_csv_files(num_files=2, output_dir=tmp_path)
    _upload(s3, tmp_path)
    run_pipeline(generate=False)
    before = _count(conn, "SELECT COUNT(*) FROM transactions")

    run_pipeline(generate=False)  # anti-doublon (hash du fichier)
    assert _count(conn, "SELECT COUNT(*) FROM transactions") == before
    assert _count(conn, "SELECT COUNT(*) FROM processed_files") == 2


def test_invalid_rows_are_rejected_and_reported(
    conn: Connection, s3: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = create_csv_files(num_files=3, output_dir=tmp_path, corrupt=True)
    csv_rows = load_all_csv_from_directory(tmp_path)
    _upload(s3, tmp_path)

    report = run_pipeline(generate=False)  # va au bout : les lignes invalides sont rejetées

    # 3 montants négatifs (-50.00) + 1 montant INVALID_AMOUNT dans le dernier fichier
    assert len(report.rejected) == 4
    assert _count(conn, "SELECT COUNT(*) FROM transactions") == len(csv_rows) - 4
    assert _count(conn, "SELECT COUNT(*) FROM transactions WHERE montant <= 0") == 0
    assert _count(conn, "SELECT COUNT(*) FROM processed_files") == len(files)

    out = capsys.readouterr().out
    assert "4 ligne(s) rejetée(s)" in out and "INVALID_AMOUNT" in out


def test_file_with_wrong_header_is_not_inserted(
    conn: Connection, s3: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    s3.put_object(Bucket=get_bucket_name(), Key="mauvais.csv", Body=b"a,b\n1,2\n")

    assert main() == 1
    assert "mauvais.csv" in capsys.readouterr().err
    assert _count(conn, "SELECT COUNT(*) FROM transactions") == 0
    assert _count(conn, "SELECT COUNT(*) FROM processed_files") == 0


def test_end_to_end_generation_minio_then_mysql(conn: Connection, s3: Any) -> None:
    """Génération CSV -> MinIO -> lecture MinIO -> traitement -> MySQL."""
    run_pipeline()  # generate=True

    keys = list_csv_keys(s3, get_bucket_name())
    assert len(keys) == 3  # les CSV générés sont bien dans MinIO
    rows = fetch_all(conn, "SELECT filename FROM processed_files ORDER BY filename")
    assert [r[0] for r in rows] == keys
    assert _count(conn, "SELECT COUNT(*) FROM transactions") > 0

    run_pipeline(generate=False)  # mêmes fichiers : rien de nouveau
    assert _count(conn, "SELECT COUNT(*) FROM processed_files") == 3


def test_minio_unreachable_stops_cleanly_with_explicit_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MINIO_ENDPOINT", "http://localhost:1")  # port fermé
    monkeypatch.setenv("MINIO_BUCKET", "bucket-inexistant-test")
    monkeypatch.setenv("MINIO_ROOT_USER", "x")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "x")
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("RETRY_DELAY_SECONDS", "0")

    assert main() == 1
    err = capsys.readouterr().err
    assert "ERREUR" in err and "MinIO" in err and "2 tentative" in err


def test_mysql_unreachable_stops_cleanly_with_explicit_error(
    s3: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MYSQL_PORT", "1")  # port fermé
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("RETRY_DELAY_SECONDS", "0")

    assert main() == 1
    err = capsys.readouterr().err
    assert "ERREUR" in err and "connexion à MySQL" in err and "2 tentative" in err

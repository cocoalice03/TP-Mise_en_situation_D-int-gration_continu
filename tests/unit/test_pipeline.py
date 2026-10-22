from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pymysql
import pytest

from src import pipeline
from src.generator import create_csv_files
from src.loader import load_csv_file
from src.retry import RetryExhaustedError
from src.storage import list_csv_keys, upload_files
from tests.unit.conftest import BUCKET


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Remplace la couche MySQL par un faux en mémoire."""
    state: dict[str, Any] = {"hashes": set(), "rows": 0, "conn": MagicMock()}

    def insert(transactions: list[Any], filename: str, h: str) -> int:
        state["hashes"].add(h)
        state["rows"] += len(transactions)
        return len(transactions)

    monkeypatch.setattr(pipeline, "get_connection", lambda: state["conn"])
    monkeypatch.setattr(pipeline, "init_db", lambda conn: None)
    monkeypatch.setattr(pipeline, "is_file_processed", lambda conn, h: h in state["hashes"])
    monkeypatch.setattr(pipeline, "insert_transactions_with_retry", insert)
    return state


def test_pipeline_generates_uploads_then_reads_from_minio(
    s3: Any, fake_db: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    pipeline.run_pipeline()
    assert len(list_csv_keys(s3, BUCKET)) == 3  # généré puis envoyé dans le bucket
    assert len(fake_db["hashes"]) == 3
    assert fake_db["rows"] > 0
    assert "Transactions de plus de 5000" in capsys.readouterr().out
    fake_db["conn"].close.assert_called_once()


def test_pipeline_reads_only_from_bucket_not_local_disk(
    s3: Any, fake_db: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload_files(s3, BUCKET, create_csv_files(num_files=2, output_dir=tmp_path))
    monkeypatch.chdir(tmp_path.parent)  # aucun CSV à portée sur le disque
    pipeline.run_pipeline(generate=False)
    assert len(fake_db["hashes"]) == 2


def test_rerun_without_generation_skips_already_processed_files(
    s3: Any, fake_db: dict[str, Any]
) -> None:
    pipeline.run_pipeline()
    rows = fake_db["rows"]
    report = pipeline.run_pipeline(generate=False)  # mêmes fichiers dans le bucket
    assert fake_db["rows"] == rows
    assert report.files_processed == 0 and report.files_skipped == 3


def test_each_run_generates_new_files_without_overwriting_previous_ones(
    s3: Any, fake_db: dict[str, Any]
) -> None:
    pipeline.run_pipeline()
    first_keys = list_csv_keys(s3, BUCKET)
    rows_after_first = fake_db["rows"]

    report = pipeline.run_pipeline()
    second_keys = list_csv_keys(s3, BUCKET)

    assert len(first_keys) == 3 and len(second_keys) == 6  # rien n'est écrasé
    assert set(first_keys) < set(second_keys)
    assert report.files_processed == 3 and report.files_skipped == 3
    assert fake_db["rows"] > rows_after_first  # de nouvelles transactions sont traitées


@pytest.fixture
def no_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() traite uniquement ce qui est déjà dans le bucket."""
    original = pipeline.run_pipeline
    monkeypatch.setattr(pipeline, "run_pipeline", lambda: original(generate=False))


def test_invalid_rows_are_rejected_reported_and_not_inserted(
    s3: Any,
    fake_db: dict[str, Any],
    no_generation: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    files = create_csv_files(num_files=3, output_dir=tmp_path, corrupt=True)
    total_rows = sum(len(load_csv_file(f)) for f in files)
    upload_files(s3, BUCKET, files)

    assert pipeline.main() == 0  # la pipeline va au bout, les lignes invalides sont rejetées

    out = capsys.readouterr().out
    # Chaque fichier contient le -50.00 injecté ; le dernier a aussi INVALID_AMOUNT : 4 rejets.
    assert "4 ligne(s) rejetée(s)" in out
    assert "transactions_batch_1.csv, ligne 3, colonne montant (valeur '-50.00')" in out
    assert "transactions_batch_3.csv, ligne 2, colonne montant (valeur 'INVALID_AMOUNT')" in out
    assert f"{total_rows - 4} transaction(s) insérée(s), 4 rejetée(s)" in out
    # Seules les lignes valides arrivent en base.
    assert fake_db["rows"] == total_rows - 4
    assert len(fake_db["hashes"]) == 3


def test_run_pipeline_returns_report(s3: Any, fake_db: dict[str, Any]) -> None:
    report = pipeline.run_pipeline()
    assert report.files_processed == 3 and report.files_skipped == 0
    assert len(report.rejected) == 3  # un -50.00 par fichier
    assert all(item.errors[0].column == "montant" for _, item in report.rejected)
    assert all(float(t["montant"]) > 0 for t in report.inserted)


def test_file_with_no_valid_row_is_not_inserted(
    s3: Any, fake_db: dict[str, Any], no_generation: None, capsys: pytest.CaptureFixture[str]
) -> None:
    header = "datetime_transaction,iban_origine,pays_source,banque_source,iban_destinataire,pays_destinataire,montant\n"
    bad = "2026-10-01 10:00:00,FR7611111111111111111111,FR,BNP,DE7622222222222222222222,DE,-5.00\n"
    s3.put_object(Bucket=BUCKET, Key="tout_invalide.csv", Body=(header + bad).encode())

    assert pipeline.main() == 0

    assert "aucune ligne valide" in capsys.readouterr().out
    assert fake_db["hashes"] == set() and fake_db["rows"] == 0


def test_file_with_wrong_header_stops_the_pipeline(
    s3: Any, fake_db: dict[str, Any], no_generation: None, capsys: pytest.CaptureFixture[str]
) -> None:
    s3.put_object(Bucket=BUCKET, Key="mauvais_entete.csv", Body=b"a,b\n1,2\n")

    assert pipeline.main() == 1
    err = capsys.readouterr().err
    assert "ERREUR" in err and "mauvais_entete.csv" in err and "colonnes manquantes" in err


def test_unreadable_file_is_reported_as_validation_error(
    s3: Any,
    fake_db: dict[str, Any],
    no_generation: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    s3.put_object(Bucket=BUCKET, Key="binaire.csv", Body=b"\xff\xfe\x00\x01")

    assert pipeline.main() == 1
    assert "binaire.csv" in capsys.readouterr().err
    assert fake_db["rows"] == 0


def test_main_stops_cleanly_with_explicit_error_when_retries_exhausted(
    s3: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def down() -> None:
        raise pymysql.err.OperationalError(2003, "Can't connect to MySQL server")

    monkeypatch.setattr(pipeline, "get_connection", down)
    assert pipeline.main() == 1
    err = capsys.readouterr().err
    assert "ERREUR" in err and "connexion à MySQL" in err and "3 tentative" in err


def test_main_reports_missing_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MINIO_ROOT_USER", "")  # variable obligatoire absente
    monkeypatch.setenv("MINIO_ENDPOINT", "http://x")
    assert pipeline.main() == 1
    assert "MINIO_ROOT_USER" in capsys.readouterr().err

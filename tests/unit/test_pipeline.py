from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src import pipeline
from src.generator import create_csv_files


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Remplace la couche base de données par un faux en mémoire."""
    state: dict[str, Any] = {"hashes": set(), "rows": 0, "conn": MagicMock()}

    def insert(conn: Any, transactions: list[Any], filename: str, h: str) -> int:
        state["hashes"].add(h)
        state["rows"] += len(transactions)
        return len(transactions)

    monkeypatch.setattr(pipeline, "get_connection", lambda: state["conn"])
    monkeypatch.setattr(pipeline, "init_db", lambda conn: None)
    monkeypatch.setattr(pipeline, "is_file_processed", lambda conn, h: h in state["hashes"])
    monkeypatch.setattr(pipeline, "insert_transactions", insert)
    return state


def test_run_pipeline_inserts_each_file(
    tmp_path: Path, fake_db: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    create_csv_files(num_files=2, output_dir=tmp_path)
    pipeline.run_pipeline(str(tmp_path))
    assert "Transactions de plus de 5000" in capsys.readouterr().out
    assert len(fake_db["hashes"]) == 2
    assert fake_db["rows"] > 0
    fake_db["conn"].close.assert_called_once()


def test_run_pipeline_skips_already_processed_files(
    tmp_path: Path, fake_db: dict[str, Any]
) -> None:
    create_csv_files(num_files=2, output_dir=tmp_path)
    pipeline.run_pipeline(str(tmp_path))
    rows = fake_db["rows"]
    pipeline.run_pipeline(str(tmp_path))
    assert fake_db["rows"] == rows

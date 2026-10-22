from datetime import datetime
from pathlib import Path

from src.generator import create_csv_files
from src.loader import load_csv_file


def _contents(files: list[Path]) -> list[str]:
    return [f.read_text(encoding="utf-8") for f in files]


def test_default_generation_is_reproducible(tmp_path: Path) -> None:
    a = create_csv_files(output_dir=tmp_path / "a")
    b = create_csv_files(output_dir=tmp_path / "b")
    assert [f.name for f in a] == ["transactions_batch_1.csv", "transactions_batch_2.csv", "transactions_batch_3.csv"]
    assert _contents(a) == _contents(b)


def test_random_seed_produces_different_data(tmp_path: Path) -> None:
    a = create_csv_files(output_dir=tmp_path / "a", seed=None)
    b = create_csv_files(output_dir=tmp_path / "b", seed=None)
    assert _contents(a) != _contents(b)


def test_run_id_gives_unique_file_names(tmp_path: Path) -> None:
    first = create_csv_files(output_dir=tmp_path, run_id="run1")
    second = create_csv_files(output_dir=tmp_path, run_id="run2")
    names = {f.name for f in first + second}
    assert len(names) == 6
    assert "transactions_run1_batch_1.csv" in names


def test_start_date_is_used_for_transaction_dates(tmp_path: Path) -> None:
    start = datetime(2027, 3, 4, 9, 0, 0)
    [first, *_] = create_csv_files(output_dir=tmp_path, start_date=start)
    rows = load_csv_file(first)
    assert all(r["datetime_transaction"].startswith("2027-03-04") for r in rows)

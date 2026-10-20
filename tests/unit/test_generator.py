import csv
from pathlib import Path

from src.generator import create_csv_files
from src.generator.data import FIELDNAMES


def _read(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_creates_requested_files_with_5_to_10_rows(tmp_path: Path) -> None:
    files = create_csv_files(num_files=4, output_dir=tmp_path)
    assert len(files) == 4
    for f in files:
        rows = _read(f)
        assert 5 <= len(rows) <= 10
        assert list(rows[0].keys()) == FIELDNAMES


def test_is_deterministic(tmp_path: Path) -> None:
    a = create_csv_files(output_dir=tmp_path / "a")
    b = create_csv_files(output_dir=tmp_path / "b")
    assert [p.read_text(encoding="utf-8") for p in a] == [
        p.read_text(encoding="utf-8") for p in b
    ]


def test_contains_high_and_low_amounts(tmp_path: Path) -> None:
    rows = _read(create_csv_files(num_files=1, output_dir=tmp_path)[0])
    amounts = [float(r["montant"]) for r in rows]
    assert any(a > 5000 for a in amounts)
    assert any(a < 5000 for a in amounts)


def test_corrupt_only_last_file(tmp_path: Path) -> None:
    files = create_csv_files(num_files=2, output_dir=tmp_path, corrupt=True)
    assert _read(files[0])[0]["montant"] != "INVALID_AMOUNT"
    assert _read(files[1])[0]["montant"] == "INVALID_AMOUNT"

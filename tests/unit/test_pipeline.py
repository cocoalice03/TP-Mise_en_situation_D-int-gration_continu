from pathlib import Path

from src.generator import create_csv_files
from src.pipeline import run_pipeline


def test_run_pipeline_on_generated_data(tmp_path: Path, capsys) -> None:
    create_csv_files(num_files=2, output_dir=tmp_path)
    run_pipeline(str(tmp_path))
    assert "Transactions de plus de 5000" in capsys.readouterr().out

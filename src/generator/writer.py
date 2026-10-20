import csv
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path

from src.generator.data import FIELDNAMES
from src.generator.transactions import generate_transactions

logger = logging.getLogger(__name__)


def write_csv(rows: list[dict[str, str]], file_path: Path) -> None:
    with open(file_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def create_csv_files(
    num_files: int = 3,
    output_dir: str | Path = "data/raw",
    corrupt: bool = False
) -> list[Path]:
    """Génère `num_files` CSV de transactions et retourne leurs chemins."""
    # Générateur dédié pour garantir la reproductibilité dans la CI
    rng = random.Random(42)

    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    start_date = datetime(2026, 10, 1, 8, 0, 0)
    created: list[Path] = []

    for file_idx in range(1, num_files + 1):
        num_records = rng.randint(5, 10)
        file_path = path / f"transactions_batch_{file_idx}.csv"
        batch_start_time = start_date + timedelta(hours=file_idx * 2)

        transactions = generate_transactions(num_records, batch_start_time, rng)

        # Simule une corruption de données pour tester l'échec de la pipeline
        if corrupt and file_idx == num_files:
            transactions[0]["montant"] = "INVALID_AMOUNT"

        write_csv(transactions, file_path)
        logger.info("Fichier généré : %s (%d transactions)", file_path, num_records)
        created.append(file_path)

    return created

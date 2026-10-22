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


DEFAULT_START_DATE = datetime(2026, 10, 1, 8, 0, 0)


def create_csv_files(
    num_files: int = 3,
    output_dir: str | Path = "data/raw",
    corrupt: bool = False,
    seed: int | None = 42,
    run_id: str | None = None,
    start_date: datetime = DEFAULT_START_DATE,
) -> list[Path]:
    """Génère `num_files` CSV de transactions et retourne leurs chemins.

    Par défaut la génération est reproductible (graine 42, mêmes noms de fichiers),
    ce qui sert aux tests et à la CI. Pour produire de NOUVEAUX fichiers à chaque
    exécution, passer `seed=None` (graine aléatoire), un `run_id` unique (inclus
    dans les noms de fichiers, qui ne s'écrasent donc pas) et une `start_date`.
    """
    # Générateur dédié : jamais l'état global de `random`
    rng = random.Random(seed)

    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []

    for file_idx in range(1, num_files + 1):
        num_records = rng.randint(5, 10)
        name = f"transactions_batch_{file_idx}.csv"
        if run_id is not None:
            name = f"transactions_{run_id}_batch_{file_idx}.csv"
        file_path = path / name
        batch_start_time = start_date + timedelta(hours=file_idx * 2)

        transactions = generate_transactions(num_records, batch_start_time, rng)

        # Simule une corruption de données pour tester l'échec de la pipeline
        if corrupt and file_idx == num_files:
            transactions[0]["montant"] = "INVALID_AMOUNT"

        write_csv(transactions, file_path)
        logger.info("Fichier généré : %s (%d transactions)", file_path, num_records)
        created.append(file_path)

    return created

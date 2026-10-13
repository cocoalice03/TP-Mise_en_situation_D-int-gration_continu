import csv
from pathlib import Path
from typing import Any, Dict, List, Union


def load_csv_file(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Charge un seul fichier CSV et retourne une liste de dictionnaires."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Le fichier {file_path} n'existe pas.")

    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def load_all_csv_from_directory(
    directory_path: Union[str, Path], pattern: str = "*.csv"
) -> List[Dict[str, Any]]:
    """Parcourt un dossier et concatène l'ensemble des transactions CSV."""
    folder = Path(directory_path)
    if not folder.is_dir():
        raise NotADirectoryError(f"Le dossier {directory_path} n'existe pas.")

    all_transactions: List[Dict[str, Any]] = []
    for csv_file in folder.glob(pattern):
        all_transactions.extend(load_csv_file(csv_file))

    return all_transactions
import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

# Données de référence déterministes
BANQUES = {
    "FR": ["BNP Paribas", "Société Générale", "Crédit Agricole"],
    "DE": ["Deutsche Bank", "Commerzbank"],
    "ES": ["Banco Santander", "BBVA"],
}


def generate_iban(country_code: str) -> str:
    """Génère un IBAN au format valide."""
    digits = "".join([str(random.randint(0, 9)) for _ in range(20)])
    return f"{country_code}76{digits}"


def generate_transactions(
    num_transactions: int, base_time: datetime
) -> list[dict]:
    transactions = []

    for i in range(num_transactions):
        pays_src = random.choice(list(BANQUES.keys()))
        pays_dst = random.choice(list(BANQUES.keys()))
        banque_src = random.choice(BANQUES[pays_src])
        dt = base_time + timedelta(minutes=i * 5 + random.randint(1, 3))

        # Injection de cas de test spécifiques (grâce au seed, ces indices sont stables)
        if i == 0:
            montant = 15000.00  # Cas 1 : Gros montant (Alerte / Seuil)
        elif i == 1:
            montant = -50.00  # Cas 2 : Montant négatif (Anomalie)
        else:
            montant = round(random.uniform(10.0, 2500.0), 2)

        transactions.append({
            "datetime_transaction": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "iban_origine": generate_iban(pays_src),
            "pays_source": pays_src,
            "banque_source": banque_src,
            "iban_destinataire": generate_iban(pays_dst),
            "pays_destinataire": pays_dst,
            "montant": f"{montant:.2f}",
        })

    return transactions


def create_csv_files(
    num_files: int = 3,
    output_dir: str = "./data_input",
    corrupt: bool = False,
):
    # Fixer la graine pour garantir la reproductibilité dans la CI
    random.seed(42)

    path = Path(output_dir)
    path.mkdir(exist_ok=True)

    fieldnames = [
        "datetime_transaction",
        "iban_origine",
        "pays_source",
        "banque_source",
        "iban_destinataire",
        "pays_destinataire",
        "montant",
    ]

    start_date = datetime(2026, 10, 1, 8, 0, 0)

    for file_idx in range(1, num_files + 1):
        num_records = random.randint(5, 10)
        file_path = path / f"transactions_batch_{file_idx}.csv"
        batch_start_time = start_date + timedelta(hours=file_idx * 2)

        transactions = generate_transactions(num_records, batch_start_time)

        # Option : Simuler une corruption de données pour tester l'échec de la pipeline
        if corrupt and file_idx == num_files:
            # Injection d'un texte à la place d'un montant numérique
            transactions[0]["montant"] = "INVALID_AMOUNT"

        with open(file_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(transactions)

        print(f"Fichier généré : {file_path} ({num_records} transactions)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Générateur de CSV de transactions"
    )
    parser.add_argument(
        "--files", type=int, default=3, help="Nombre de fichiers"
    )
    parser.add_argument(
        "--output", type=str, default="./data_input", help="Dossier de sortie"
    )
    parser.add_argument(
        "--corrupt", action="store_true", help="Générer un fichier corrompu"
    )

    args = parser.parse_args()
    create_csv_files(
        num_files=args.files, output_dir=args.output, corrupt=args.corrupt
    )
from pprint import pprint
from pipeline.io import load_all_csv_from_directory
from pipeline.process import (
    flag_high_value_transactions,
    sum_by_banque_source,
    sum_by_iban_destinataire,
    sum_by_iban_origine,
)


def run_pipeline(data_dir: str = "./data_input"):
    # 1. Chargement des données (I/O)
    print(f"Chargement des fichiers CSV depuis : {data_dir}")
    raw_transactions = load_all_csv_from_directory(data_dir)
    print(f"Total transactions chargées : {len(raw_transactions)}\n")

    if not raw_transactions:
        print("Aucune transaction à traiter.")
        return

    # 2. Traitements fonctionnels (Fonctions pures)
    totaux_iban_origine = sum_by_iban_origine(raw_transactions)
    totaux_banque_source = sum_by_banque_source(raw_transactions)
    totaux_iban_destinataire = sum_by_iban_destinataire(raw_transactions)
    transactions_flaguees = flag_high_value_transactions(
        raw_transactions, threshold=5000.0
    )

    # 3. Affichage des résultats
    print("--- Somme par Banque Source ---")
    pprint(totaux_banque_source)

    print("\n--- Somme par IBAN Origine (Top 3) ---")
    pprint(dict(list(totaux_iban_origine.items())[:3]))

    print("\n--- Somme par IBAN Destinataire (Top 3) ---")
    pprint(dict(list(totaux_iban_destinataire.items())[:3]))

    high_value_count = sum(
        1 for t in transactions_flaguees if t["is_high_value"]
    )
    print(
        f"\n--- Transactions de plus de 5000 € --- : {high_value_count} détectée(s)"
    )


if __name__ == "__main__":
    run_pipeline()
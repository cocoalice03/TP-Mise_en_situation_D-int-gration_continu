from pprint import pprint
from typing import Any

from pymysql.connections import Connection

from src.database import get_connection, init_db, insert_transactions, is_file_processed
from src.loader import compute_file_hash, list_csv_files, load_csv_file
from src.processing import (
    flag_high_value_transactions,
    sum_by_banque_source,
    sum_by_iban_destinataire,
    sum_by_iban_origine,
)


def run_pipeline(data_dir: str = "data/raw") -> None:
    conn = get_connection()
    try:
        new_transactions = _process_files(conn, data_dir)
    finally:
        conn.close()

    _display_results(new_transactions)


def _process_files(conn: Connection, data_dir: str) -> list[dict[str, Any]]:
    init_db(conn)
    new_transactions: list[dict[str, Any]] = []

    # 1. Chargement des fichiers non encore traités (anti-doublon) + insertion
    print(f"Chargement des fichiers CSV depuis : {data_dir}")
    for csv_file in list_csv_files(data_dir):
        file_hash = compute_file_hash(csv_file)
        if is_file_processed(conn, file_hash):
            print(f"Fichier déjà traité, ignoré : {csv_file.name}")
            continue

        # 2. Traitement fonctionnel (fonctions pures) puis insertion en base
        flagged = flag_high_value_transactions(
            load_csv_file(csv_file), threshold=5000.0
        )
        inserted = insert_transactions(conn, flagged, csv_file.name, file_hash)
        print(f"{csv_file.name} : {inserted} transactions insérées en base.")
        new_transactions.extend(flagged)

    return new_transactions


def _display_results(new_transactions: list[dict[str, Any]]) -> None:
    if not new_transactions:
        print("Aucune nouvelle transaction à traiter.")
        return

    # 3. Affichage des résultats sur les nouvelles données
    print("\n--- Somme par Banque Source ---")
    pprint(sum_by_banque_source(new_transactions))

    print("\n--- Somme par IBAN Origine (Top 3) ---")
    pprint(dict(list(sum_by_iban_origine(new_transactions).items())[:3]))

    print("\n--- Somme par IBAN Destinataire (Top 3) ---")
    pprint(dict(list(sum_by_iban_destinataire(new_transactions).items())[:3]))

    high_value_count = sum(1 for t in new_transactions if t["is_high_value"])
    print(
        f"\n--- Transactions de plus de 5000 € --- : {high_value_count} détectée(s)"
    )


if __name__ == "__main__":
    run_pipeline()

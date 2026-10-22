"""Pipeline : Génération CSV -> MinIO -> lecture MinIO -> traitement -> MySQL."""
import csv
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from pprint import pprint
from typing import Any

from pymysql.connections import Connection

from src.config import MissingConfigError
from src.database import (
    DB_RETRY_ON,
    get_connection,
    init_db,
    insert_transactions_with_retry,
    is_file_processed,
    is_retryable_db_error,
)
from src.generator import create_csv_files
from src.loader import compute_bytes_hash, parse_csv_bytes
from src.processing import (
    flag_high_value_transactions,
    sum_by_banque_source,
    sum_by_iban_destinataire,
    sum_by_iban_origine,
)
from src.retry import RetryExhaustedError, call_with_retry
from src.validation import (
    FieldError,
    RejectedRow,
    ValidationError,
    ValidationResult,
    validate_rows,
)
from src.storage import (
    ensure_bucket,
    get_bucket_name,
    get_s3_client,
    list_csv_keys,
    read_object,
    upload_files,
)


@dataclass
class PipelineReport:
    """Résultat d'une exécution, affiché en fin de pipeline."""

    inserted: list[dict[str, Any]] = field(default_factory=list)  # lignes insérées
    rejected: list[tuple[str, RejectedRow]] = field(default_factory=list)  # (fichier, ligne)
    files_processed: int = 0
    files_skipped: int = 0
    files_without_valid_row: int = 0


def run_pipeline(generate: bool = True) -> PipelineReport:
    """Exécute la pipeline.

    `generate=True` génère des CSV et les envoie dans MinIO avant le traitement.
    Le traitement lit ensuite uniquement depuis MinIO (jamais le disque local).
    """
    client = get_s3_client()
    bucket = get_bucket_name()
    ensure_bucket(client, bucket)

    if generate:
        _generate_and_upload(client, bucket)

    conn = call_with_retry(
        _open_database,
        operation="connexion à MySQL",
        retry_on=DB_RETRY_ON,
        is_retryable=is_retryable_db_error,
    )
    try:
        report = _process_files(conn, client, bucket)
    finally:
        conn.close()

    _display_results(report)
    return report


def _generate_and_upload(client: Any, bucket: str) -> None:
    # 1. Génération des CSV dans un dossier temporaire, puis envoi dans MinIO
    with tempfile.TemporaryDirectory() as tmp:
        files = create_csv_files(output_dir=Path(tmp))
        keys = upload_files(client, bucket, files)
    print(f"{len(keys)} fichiers envoyés dans MinIO (bucket {bucket}).")


def _open_database() -> Connection:
    conn = get_connection()
    try:
        init_db(conn)
    except Exception:
        conn.close()
        raise
    return conn


def _process_files(conn: Connection, client: Any, bucket: str) -> PipelineReport:
    report = PipelineReport()

    # 2. Lecture depuis MinIO des fichiers non encore traités (anti-doublon)
    print(f"Lecture des fichiers CSV depuis MinIO (bucket {bucket})")
    for key in list_csv_keys(client, bucket):
        data = read_object(client, bucket, key)
        file_hash = compute_bytes_hash(data)
        if is_file_processed(conn, file_hash):
            print(f"Fichier déjà traité, ignoré : {key}")
            report.files_skipped += 1
            continue

        # 3. Validation : les lignes invalides sont rejetées, les autres continuent
        result = _parse_and_validate(data, key)
        report.rejected.extend((key, r) for r in result.rejected)
        if not result.valid_rows:
            print(f"{key} : aucune ligne valide, fichier non inséré.")
            report.files_without_valid_row += 1
            continue

        # 4. Traitement fonctionnel (fonctions pures) puis insertion en base
        flagged = flag_high_value_transactions(result.valid_rows, threshold=5000.0)
        inserted = insert_transactions_with_retry(flagged, key, file_hash)
        if inserted is None:
            print(f"Fichier déjà enregistré par un autre traitement, ignoré : {key}")
            report.files_skipped += 1
            continue
        rejected_note = f", {len(result.rejected)} rejetée(s)" if result.rejected else ""
        print(f"{key} : {inserted} transactions insérées en base{rejected_note}.")
        report.files_processed += 1
        report.inserted.extend(flagged)

    return report


def _parse_and_validate(data: bytes, key: str) -> ValidationResult:
    """Lit le CSV puis le valide ligne par ligne.

    Lève `ValidationError` si le fichier entier est inexploitable (illisible,
    vide, en-tête incorrect).
    """
    try:
        rows = parse_csv_bytes(data)
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValidationError(
            key, [FieldError(1, "*", None, f"fichier illisible (UTF-8 / CSV attendu) : {error}")]
        ) from error
    return validate_rows(rows, source=key)


def _display_results(report: PipelineReport) -> None:
    # 5. Rapport de validation : ce qui a été rejeté et pourquoi
    inserted = len(report.inserted)
    rejected = len(report.rejected)
    print("\n--- Validation ---")
    if report.rejected:
        print(f"{rejected} ligne(s) rejetée(s) (non insérées) :")
        for source, item in report.rejected:
            for error in item.errors:
                print(f"  - {source}, {error}")
    else:
        print("Aucune ligne rejetée.")
    print(
        f"Résumé : {inserted} transaction(s) insérée(s), {rejected} rejetée(s), "
        f"{report.files_processed} fichier(s) traité(s), {report.files_skipped} déjà traité(s)."
    )

    if not report.inserted:
        print("Aucune nouvelle transaction à traiter.")
        return

    # 6. Affichage des résultats sur les nouvelles données (lignes valides uniquement)
    print("\n--- Somme par Banque Source ---")
    pprint(sum_by_banque_source(report.inserted))

    print("\n--- Somme par IBAN Origine (Top 3) ---")
    pprint(dict(list(sum_by_iban_origine(report.inserted).items())[:3]))

    print("\n--- Somme par IBAN Destinataire (Top 3) ---")
    pprint(dict(list(sum_by_iban_destinataire(report.inserted).items())[:3]))

    high_value_count = sum(1 for t in report.inserted if t["is_high_value"])
    print(
        f"\n--- Transactions de plus de 5000 € --- : {high_value_count} détectée(s)"
    )


def main() -> int:
    """Point d'entrée : arrêt propre avec un message explicite en cas d'échec."""
    try:
        run_pipeline()
    except (RetryExhaustedError, MissingConfigError, ValidationError) as error:
        print(f"ERREUR : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

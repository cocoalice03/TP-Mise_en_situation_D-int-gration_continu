"""Package de traitement des pipelines de transactions financières."""

from pipeline.io import load_all_csv_from_directory, load_csv_file
from pipeline.process import (
    flag_high_value_transactions,
    sum_by_banque_source,
    sum_by_iban_destinataire,
    sum_by_iban_origine,
)

# Liste des symboles exportés explicitement lors d'un `from pipeline import *`
__all__ = [
    "load_csv_file",
    "load_all_csv_from_directory",
    "sum_by_iban_origine",
    "sum_by_banque_source",
    "sum_by_iban_destinataire",
    "flag_high_value_transactions",
]
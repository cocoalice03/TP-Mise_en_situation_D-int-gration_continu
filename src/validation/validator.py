"""Validation des transactions lues dans un CSV (spec §4.3).

Fonctions pures : aucune lecture de fichier, MinIO ou MySQL. Elles prennent les
lignes telles que lues (toutes les valeurs sont des chaînes) et retournent la
liste exhaustive des erreurs, pour que l'utilisateur corrige tout en une fois.
"""
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

EXPECTED_COLUMNS = (
    "datetime_transaction",
    "iban_origine",
    "pays_source",
    "banque_source",
    "iban_destinataire",
    "pays_destinataire",
    "montant",
)

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
IBAN_PATTERN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$")
MAX_BANK_NAME_LENGTH = 100
MAX_AMOUNT = Decimal("9999999999.99")  # colonne DECIMAL(12,2)


@dataclass(frozen=True)
class FieldError:
    """Une erreur de validation, localisée dans le fichier."""

    line: int  # numéro de ligne dans le CSV (l'en-tête est la ligne 1) ; 1 = fichier
    column: str
    value: Any
    message: str

    def __str__(self) -> str:
        if self.column == "*":
            return f"ligne {self.line} : {self.message}"
        return f"ligne {self.line}, colonne {self.column} (valeur {self.value!r}) : {self.message}"


@dataclass(frozen=True)
class RejectedRow:
    """Une ligne rejetée : elle n'est ni traitée ni insérée."""

    line: int
    row: dict[str, Any]
    errors: list[FieldError]


@dataclass(frozen=True)
class ValidationResult:
    valid_rows: list[dict[str, Any]]
    rejected: list[RejectedRow]


class ValidationError(Exception):
    """Données invalides : le fichier ne doit être ni traité ni inséré."""

    def __init__(self, source: str, errors: list[FieldError]) -> None:
        self.source = source
        self.errors = errors
        shown = errors[:20]
        lines = "\n".join(f"  - {e}" for e in shown)
        more = f"\n  ... et {len(errors) - len(shown)} autre(s) erreur(s)" if len(errors) > len(shown) else ""
        super().__init__(
            f"Fichier {source} invalide : {len(errors)} erreur(s) de validation\n{lines}{more}"
        )


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _check_datetime(line: int, value: str) -> list[FieldError]:
    try:
        datetime.strptime(value, DATETIME_FORMAT)
    except ValueError:
        return [FieldError(line, "datetime_transaction", value, "date invalide, format attendu AAAA-MM-JJ HH:MM:SS")]
    return []


def _check_iban(line: int, column: str, value: str, country: str | None) -> list[FieldError]:
    if not IBAN_PATTERN.match(value):
        return [FieldError(line, column, value, "IBAN invalide (2 lettres majuscules, 2 chiffres, puis 11 à 30 caractères alphanumériques)")]
    if country and COUNTRY_PATTERN.match(country) and value[:2] != country:
        return [FieldError(line, column, value, f"le préfixe pays de l'IBAN ({value[:2]}) ne correspond pas au pays {country}")]
    return []


def _check_country(line: int, column: str, value: str) -> list[FieldError]:
    if not COUNTRY_PATTERN.match(value):
        return [FieldError(line, column, value, "code pays invalide (2 lettres majuscules attendues)")]
    return []


def _check_amount(line: int, value: str) -> list[FieldError]:
    try:
        amount = Decimal(value.strip())
    except InvalidOperation:
        return [FieldError(line, "montant", value, "le montant n'est pas un nombre")]
    if not amount.is_finite():
        return [FieldError(line, "montant", value, "le montant doit être un nombre fini")]
    if amount <= 0:
        return [FieldError(line, "montant", value, "le montant doit être strictement positif")]
    if amount != amount.quantize(Decimal("0.01")):
        return [FieldError(line, "montant", value, "le montant ne peut avoir plus de 2 décimales")]
    if amount > MAX_AMOUNT:
        return [FieldError(line, "montant", value, f"le montant dépasse le maximum autorisé ({MAX_AMOUNT})")]
    return []


def _validate_structure(rows: list[dict[str, Any]]) -> list[FieldError]:
    """Erreurs qui concernent le fichier entier (vide, en-tête incorrect)."""
    if not rows:
        return [FieldError(1, "*", None, "le fichier ne contient aucune transaction")]

    columns = {c for c in rows[0] if c is not None}
    missing = [c for c in EXPECTED_COLUMNS if c not in columns]
    unexpected = sorted(columns - set(EXPECTED_COLUMNS))
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"colonnes manquantes : {', '.join(missing)}")
        if unexpected:
            details.append(f"colonnes inattendues : {', '.join(unexpected)}")
        return [FieldError(1, "*", None, "en-tête invalide, " + " ; ".join(details))]
    return []


def _validate_row(line: int, row: dict[str, Any]) -> list[FieldError]:
    if None in row:
        return [FieldError(line, "*", None, "la ligne contient plus de valeurs que de colonnes")]

    errors: list[FieldError] = []
    blank = [c for c in EXPECTED_COLUMNS if _is_blank(row.get(c))]
    for column in blank:
        errors.append(FieldError(line, column, row.get(column), "valeur manquante"))

    def present(column: str) -> str | None:
        return None if column in blank else str(row[column]).strip()

    if (v := present("datetime_transaction")) is not None:
        errors += _check_datetime(line, v)
    if (v := present("pays_source")) is not None:
        errors += _check_country(line, "pays_source", v)
    if (v := present("pays_destinataire")) is not None:
        errors += _check_country(line, "pays_destinataire", v)
    if (v := present("iban_origine")) is not None:
        errors += _check_iban(line, "iban_origine", v, present("pays_source"))
    if (v := present("iban_destinataire")) is not None:
        errors += _check_iban(line, "iban_destinataire", v, present("pays_destinataire"))
    if (v := present("banque_source")) is not None and len(v) > MAX_BANK_NAME_LENGTH:
        errors.append(FieldError(line, "banque_source", v, f"nom de banque trop long (max {MAX_BANK_NAME_LENGTH} caractères)"))
    if (v := present("montant")) is not None:
        errors += _check_amount(line, v)
    return errors


def validate_transactions(rows: list[dict[str, Any]]) -> list[FieldError]:
    """Retourne toutes les erreurs de validation (liste vide si les données sont valides)."""
    structure = _validate_structure(rows)
    if structure:
        return structure
    errors: list[FieldError] = []
    for index, row in enumerate(rows):
        errors += _validate_row(index + 2, row)  # l'en-tête occupe la ligne 1
    return errors


def validate_rows(rows: list[dict[str, Any]], source: str = "<inconnu>") -> ValidationResult:
    """Sépare les lignes valides des lignes rejetées.

    Une ligne invalide est rejetée seule (avec toutes ses erreurs) : les autres
    lignes du fichier restent utilisables. Un problème qui concerne le fichier
    entier (vide, en-tête incorrect) lève `ValidationError` : rien n'est exploitable.
    """
    structure = _validate_structure(rows)
    if structure:
        raise ValidationError(source, structure)

    valid: list[dict[str, Any]] = []
    rejected: list[RejectedRow] = []
    for index, row in enumerate(rows):
        line = index + 2
        errors = _validate_row(line, row)
        if errors:
            rejected.append(RejectedRow(line, row, errors))
        else:
            valid.append(row)
    return ValidationResult(valid, rejected)


def validate_or_raise(rows: list[dict[str, Any]], source: str = "<inconnu>") -> None:
    """Lève `ValidationError` (avec toutes les erreurs) si les données sont invalides."""
    errors = validate_transactions(rows)
    if errors:
        raise ValidationError(source, errors)

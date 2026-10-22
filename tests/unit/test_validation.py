from pathlib import Path
from typing import Any

import pytest

from src.generator import create_csv_files
from src.loader import load_csv_file
from src.validation import (
    ValidationError,
    validate_or_raise,
    validate_rows,
    validate_transactions,
)

VALID: dict[str, Any] = {
    "datetime_transaction": "2026-10-01 10:01:00",
    "iban_origine": "FR7611111111111111111111",
    "pays_source": "FR",
    "banque_source": "BNP Paribas",
    "iban_destinataire": "DE7622222222222222222222",
    "pays_destinataire": "DE",
    "montant": "15000.00",
}


def row(**changes: Any) -> dict[str, Any]:
    return {**VALID, **changes}


def errors_for(**changes: Any) -> list[tuple[int, str]]:
    return [(e.line, e.column) for e in validate_transactions([row(**changes)])]


def test_valid_rows_have_no_error() -> None:
    assert validate_transactions([row(), row(montant="0.01"), row(montant="5000")]) == []


def test_generated_files_contain_exactly_the_injected_negative_amount(tmp_path: Path) -> None:
    """Le générateur injecte -50.00 (2e ligne de données) : seule cette ligne est invalide."""
    for f in create_csv_files(num_files=3, output_dir=tmp_path):
        errors = validate_transactions(load_csv_file(f))
        assert [(e.line, e.column, e.value) for e in errors] == [(3, "montant", "-50.00")]


def test_corrupted_generated_file_has_one_more_invalid_row(tmp_path: Path) -> None:
    files = create_csv_files(num_files=2, output_dir=tmp_path, corrupt=True)
    errors = validate_transactions(load_csv_file(files[1]))
    assert [(e.line, e.column, e.value) for e in errors] == [
        (2, "montant", "INVALID_AMOUNT"),
        (3, "montant", "-50.00"),
    ]


def test_empty_file_is_invalid() -> None:
    [error] = validate_transactions([])
    assert "aucune transaction" in error.message


@pytest.mark.parametrize(
    "bad",
    ["abc", "", "12,5", "NaN", "Infinity", "0", "0.00", "-50.00", "10.123", "99999999999.00"],
)
def test_invalid_amounts(bad: str) -> None:
    assert errors_for(montant=bad) == [(2, "montant")]


@pytest.mark.parametrize("good", ["0.01", "1", "42.5", "15000.00", " 12.00 ", "9999999999.99"])
def test_valid_amounts(good: str) -> None:
    assert errors_for(montant=good) == []


@pytest.mark.parametrize("bad", ["2026-13-01 10:00:00", "2026-10-01", "01/10/2026 10:00", "hier", ""])
def test_invalid_datetime(bad: str) -> None:
    assert errors_for(datetime_transaction=bad) == [(2, "datetime_transaction")]


@pytest.mark.parametrize("bad", ["FR76", "fr7611111111111111111111", "1234567890123456", "FR7611111111111111111111!!"])
def test_invalid_iban(bad: str) -> None:
    assert (2, "iban_origine") in errors_for(iban_origine=bad)


def test_iban_prefix_must_match_country() -> None:
    errors = validate_transactions([row(pays_source="ES")])
    assert [(e.column, "ne correspond pas" in e.message) for e in errors] == [("iban_origine", True)]
    errors = validate_transactions([row(pays_destinataire="FR")])
    assert [e.column for e in errors] == ["iban_destinataire"]


@pytest.mark.parametrize("bad", ["F", "FRA", "fr", "12"])
def test_invalid_country(bad: str) -> None:
    assert (2, "pays_source") in errors_for(pays_source=bad)


def test_missing_values_are_reported() -> None:
    errors = validate_transactions([row(banque_source="  ", montant=None)])
    assert {(e.column, e.message) for e in errors} == {
        ("banque_source", "valeur manquante"),
        ("montant", "valeur manquante"),
    }


def test_header_must_match_expected_columns() -> None:
    bad_header = [{k: v for k, v in VALID.items() if k != "montant"} | {"extra": "x"}]
    [error] = validate_transactions(bad_header)
    assert "montant" in error.message and "extra" in error.message


def test_row_with_too_many_values() -> None:
    too_long: dict[Any, Any] = {**VALID, None: ["surplus"]}
    [error] = validate_transactions([too_long])
    assert error.line == 2 and "plus de valeurs" in error.message


def test_all_errors_are_collected_with_line_numbers() -> None:
    rows = [row(), row(montant="abc"), row(), row(montant="-1", pays_source="XX")]
    found = [(e.line, e.column) for e in validate_transactions(rows)]
    assert (3, "montant") in found
    assert (5, "montant") in found and (5, "iban_origine") in found


def test_validate_or_raise_message_is_explicit() -> None:
    with pytest.raises(ValidationError) as info:
        validate_or_raise([row(montant="INVALID_AMOUNT")], source="batch_3.csv")
    message = str(info.value)
    assert "batch_3.csv" in message and "ligne 2" in message
    assert "montant" in message and "INVALID_AMOUNT" in message
    assert len(info.value.errors) == 1


def test_validate_or_raise_accepts_valid_data() -> None:
    validate_or_raise([row()], source="ok.csv")


def test_validation_does_not_mutate_input() -> None:
    rows = [row(montant=" 12.00 ")]
    snapshot = [dict(r) for r in rows]
    validate_transactions(rows)
    assert rows == snapshot


# --- Rejet par ligne -------------------------------------------------------


def test_validate_rows_splits_valid_and_rejected_rows() -> None:
    rows = [row(), row(montant="-50.00"), row(montant="12.00"), row(montant="abc", pays_source="X")]

    result = validate_rows(rows, source="f.csv")

    assert result.valid_rows == [rows[0], rows[2]]
    assert [r.line for r in result.rejected] == [3, 5]
    assert result.rejected[0].row is rows[1]
    assert [e.column for e in result.rejected[1].errors] == ["pays_source", "montant"]


def test_validate_rows_without_error_rejects_nothing() -> None:
    result = validate_rows([row(), row()])
    assert len(result.valid_rows) == 2 and result.rejected == []


def test_validate_rows_all_invalid() -> None:
    result = validate_rows([row(montant="0"), row(montant="x")])
    assert result.valid_rows == [] and len(result.rejected) == 2


@pytest.mark.parametrize("rows", [[], [{"montant": "1"}]])
def test_validate_rows_raises_when_the_whole_file_is_unusable(rows: list[dict[str, Any]]) -> None:
    with pytest.raises(ValidationError) as info:
        validate_rows(rows, source="mauvais.csv")
    assert "mauvais.csv" in str(info.value)


def test_validate_rows_does_not_mutate_input() -> None:
    rows = [row(), row(montant="-1")]
    snapshot = [dict(r) for r in rows]
    validate_rows(rows)
    assert rows == snapshot

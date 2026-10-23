"""Tests unitaires du traitement (spec §4.4) : fonctions pures, sans fichier, MinIO ni MySQL."""
import copy
from typing import Any

import pytest

from src.processing import (
    aggregate_by_key,
    flag_high_value_transactions,
    sum_by_banque_source,
    sum_by_iban_destinataire,
    sum_by_iban_origine,
)

A, B = "FR7611111111111111111111", "DE7622222222222222222222"
C, X = "ES7633333333333333333333", "FR7644444444444444444444"


def tx(montant: str, origine: str = A, banque: str = "BNP Paribas", destinataire: str = X) -> dict[str, Any]:
    return {
        "datetime_transaction": "2026-10-01 10:00:00",
        "iban_origine": origine,
        "pays_source": origine[:2],
        "banque_source": banque,
        "iban_destinataire": destinataire,
        "pays_destinataire": destinataire[:2],
        "montant": montant,
    }


# Mêmes données et mêmes totaux (calculés à la main) que le test d'intégration.
KNOWN = [
    tx("15000.00", A, "BNP Paribas", X),
    tx("42.50", A, "BNP Paribas", C),
    tx("5000.00", B, "Commerzbank", C),
    tx("5000.01", B, "Commerzbank", X),
]


# --- Flag « transaction à risque » : montant strictement supérieur au seuil ----------


@pytest.mark.parametrize(
    "montant,expected",
    [("15000.00", True), ("5000.01", True), ("5000.00", False), ("4999.99", False), ("42.50", False)],
)
def test_flag_high_value(montant: str, expected: bool) -> None:
    [flagged] = flag_high_value_transactions([tx(montant)])
    assert flagged["is_high_value"] is expected


def test_amount_equal_to_threshold_is_not_high_value() -> None:
    """Le seuil est strict : exactement 5000.00 n'est PAS une transaction à risque."""
    [flagged] = flag_high_value_transactions([tx("5000.00")], threshold=5000.0)
    assert flagged["is_high_value"] is False, (
        "5000.00 ne dépasse pas le seuil de 5000 : le flag doit être faux "
        "(le seuil est strictement supérieur)"
    )


def test_flag_uses_custom_threshold() -> None:
    rows = [tx("99.99"), tx("100.00"), tx("100.01")]
    flags = [r["is_high_value"] for r in flag_high_value_transactions(rows, threshold=100.0)]
    assert flags == [False, False, True]


def test_flag_converts_amount_to_number() -> None:
    [flagged] = flag_high_value_transactions([tx("42.50")])
    assert flagged["montant"] == 42.5 and isinstance(flagged["montant"], float)


def test_flag_keeps_other_columns() -> None:
    [flagged] = flag_high_value_transactions([tx("10.00")])
    assert flagged["iban_origine"] == A and flagged["banque_source"] == "BNP Paribas"


def test_flag_returns_new_objects_and_does_not_mutate_input() -> None:
    rows = copy.deepcopy(KNOWN)
    snapshot = copy.deepcopy(rows)
    result = flag_high_value_transactions(rows)
    assert rows == snapshot  # entrée inchangée (montants toujours des chaînes, pas de flag ajouté)
    assert all(new is not old for new, old in zip(result, rows))


def test_flag_empty_list() -> None:
    assert flag_high_value_transactions([]) == []


# --- Sommes -------------------------------------------------------------------------


def test_sum_by_iban_origine() -> None:
    assert sum_by_iban_origine(KNOWN) == {A: 15042.50, B: 10000.01}


def test_sum_by_banque_source() -> None:
    assert sum_by_banque_source(KNOWN) == {"BNP Paribas": 15042.50, "Commerzbank": 10000.01}


def test_sum_by_iban_destinataire() -> None:
    assert sum_by_iban_destinataire(KNOWN) == {X: 20000.01, C: 5042.50}


def test_sums_are_rounded_to_two_decimals() -> None:
    rows = [tx("0.10"), tx("0.20")]  # 0.1 + 0.2 = 0.30000000000000004 en flottant
    assert aggregate_by_key(rows, "iban_origine") == {A: 0.3}


def test_aggregate_by_other_value_column() -> None:
    rows = [{"banque_source": "BNP", "frais": "1.5"}, {"banque_source": "BNP", "frais": "2.25"}]
    assert aggregate_by_key(rows, "banque_source", value_key="frais") == {"BNP": 3.75}


def test_sums_of_empty_list() -> None:
    assert sum_by_iban_origine([]) == {}
    assert sum_by_banque_source([]) == {}
    assert sum_by_iban_destinataire([]) == {}


def test_sums_do_not_mutate_input() -> None:
    rows = copy.deepcopy(KNOWN)
    snapshot = copy.deepcopy(rows)
    sum_by_iban_origine(rows)
    sum_by_banque_source(rows)
    sum_by_iban_destinataire(rows)
    assert rows == snapshot


def test_sums_are_deterministic() -> None:
    assert sum_by_iban_origine(KNOWN) == sum_by_iban_origine(KNOWN)

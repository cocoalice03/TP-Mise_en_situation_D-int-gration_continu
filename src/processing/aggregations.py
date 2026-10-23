from typing import Any, Dict, List


def aggregate_by_key(
    data: List[Dict[str, Any]], key: str, value_key: str = "montant"
) -> Dict[str, float]:
    """Calcule la somme d'un champ numérique groupé par une clé spécifique.

    Fonction pure : ne mute pas `data` et produit toujours le même dictionnaire.
    """
    result: Dict[str, float] = {}
    for row in data:
        group = row[key]
        amount = float(row[value_key])
        result[group] = round(result.get(group, 0.0) + amount, 2)
    return result


def sum_by_iban_origine(data: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calcule la somme des montants envoyés par iban_origine."""
    return aggregate_by_key(data, key="iban_origine")


def sum_by_banque_source(data: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calcule la somme des montants envoyés par banque_source."""
    return aggregate_by_key(data, key="banque_source")


def sum_by_iban_destinataire(data: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calcule la somme des montants reçus par iban_destinataire."""
    return aggregate_by_key(data, key="iban_destinataire")


def flag_high_value_transactions(
    data: List[Dict[str, Any]], threshold: float = 5000.0
) -> List[Dict[str, Any]]:
    """Retourne une NOUVELLE liste de transactions.

    Ajoute un flag 'is_high_value' (True/False) si montant > threshold.
    Fonction pure : recrée de nouveaux dictionnaires pour éviter toute mutation.
    """
    flagged_data = []
    for row in data:
        # Copie superficielle pour garantir l'immutabilité de l'entrée
        new_row = row.copy()
        new_row["montant"] = float(row["montant"])
        new_row["is_high_value"] = new_row["montant"] >= threshold
        flagged_data.append(new_row)
    return flagged_data
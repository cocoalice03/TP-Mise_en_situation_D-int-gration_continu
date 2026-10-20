"""Données de référence du générateur."""

BANQUES: dict[str, list[str]] = {
    "FR": ["BNP Paribas", "Société Générale", "Crédit Agricole"],
    "DE": ["Deutsche Bank", "Commerzbank"],
    "ES": ["Banco Santander", "BBVA"],
}

FIELDNAMES: list[str] = [
    "datetime_transaction",
    "iban_origine",
    "pays_source",
    "banque_source",
    "iban_destinataire",
    "pays_destinataire",
    "montant",
]

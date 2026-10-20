import random
from datetime import datetime, timedelta

from src.generator.data import BANQUES
from src.generator.iban import generate_iban


def generate_transactions(
    num_transactions: int, base_time: datetime, rng: random.Random
) -> list[dict[str, str]]:
    transactions: list[dict[str, str]] = []

    for i in range(num_transactions):
        pays_src = rng.choice(list(BANQUES.keys()))
        pays_dst = rng.choice(list(BANQUES.keys()))
        banque_src = rng.choice(BANQUES[pays_src])
        dt = base_time + timedelta(minutes=i * 5 + rng.randint(1, 3))

        # Injection de cas de test spécifiques (stables grâce au seed)
        if i == 0:
            montant = 15000.00  # Cas 1 : gros montant (alerte / seuil)
        elif i == 1:
            montant = -50.00  # Cas 2 : montant négatif (anomalie)
        else:
            montant = round(rng.uniform(10.0, 2500.0), 2)

        transactions.append({
            "datetime_transaction": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "iban_origine": generate_iban(pays_src, rng),
            "pays_source": pays_src,
            "banque_source": banque_src,
            "iban_destinataire": generate_iban(pays_dst, rng),
            "pays_destinataire": pays_dst,
            "montant": f"{montant:.2f}",
        })

    return transactions

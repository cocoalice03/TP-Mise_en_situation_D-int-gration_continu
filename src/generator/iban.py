import random


def generate_iban(country_code: str, rng: random.Random) -> str:
    """Génère un IBAN au format valide."""
    digits = "".join(str(rng.randint(0, 9)) for _ in range(20))
    return f"{country_code}76{digits}"

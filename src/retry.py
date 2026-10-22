"""Retry générique (spec §4.8) : détecter, attendre, réessayer, s'arrêter proprement."""
import logging
import os
import time
from collections.abc import Callable
from typing import TypeVar

from src.config import load_env

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_DELAY_SECONDS = 2.0
DEFAULT_BACKOFF = 2.0


class RetryExhaustedError(RuntimeError):
    """Toutes les tentatives d'une opération ont échoué."""


def _settings() -> tuple[int, float]:
    """Lit RETRY_MAX_ATTEMPTS et RETRY_DELAY_SECONDS (non secrets, optionnels)."""
    load_env()
    attempts = int(os.environ.get("RETRY_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS))
    delay = float(os.environ.get("RETRY_DELAY_SECONDS", DEFAULT_DELAY_SECONDS))
    return max(1, attempts), max(0.0, delay)


def call_with_retry(
    func: Callable[[], T],
    *,
    operation: str,
    retry_on: tuple[type[Exception], ...],
    is_retryable: Callable[[Exception], bool] = lambda e: True,
    attempts: int | None = None,
    delay: float | None = None,
    backoff: float = DEFAULT_BACKOFF,
) -> T:
    """Exécute `func`, avec un nombre limité de tentatives.

    - Une exception qui n'est pas dans `retry_on` (ou refusée par
      `is_retryable`) est une erreur permanente : elle est relancée telle quelle.
    - Entre deux tentatives, attend `delay` secondes (multiplié par `backoff`).
      Aucune attente après la dernière tentative.
    - Si toutes les tentatives échouent, lève `RetryExhaustedError` avec un
      message explicite, chaînée à la dernière erreur.
    """
    default_attempts, default_delay = _settings()
    max_attempts = attempts if attempts is not None else default_attempts
    wait = delay if delay is not None else default_delay

    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except retry_on as error:
            if not is_retryable(error):
                raise
            if attempt == max_attempts:
                raise RetryExhaustedError(
                    f"Échec de l'opération « {operation} » après "
                    f"{max_attempts} tentative(s). Dernière erreur : "
                    f"{type(error).__name__}: {error}"
                ) from error
            logger.warning(
                "%s : tentative %d/%d échouée (%s: %s), nouvel essai dans %.1f s",
                operation, attempt, max_attempts, type(error).__name__, error, wait,
            )
            time.sleep(wait)
            wait *= backoff
    raise AssertionError("inatteignable")  # pragma: no cover

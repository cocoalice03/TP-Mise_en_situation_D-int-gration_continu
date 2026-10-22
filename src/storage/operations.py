import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from src.retry import call_with_retry

logger = logging.getLogger(__name__)

S3_RETRY_ON: tuple[type[Exception], ...] = (
    EndpointConnectionError,
    ConnectionClosedError,
    ConnectTimeoutError,
    ReadTimeoutError,
    ConnectionError,
    ClientError,
)

THROTTLING_CODES = {
    "SlowDown",
    "Throttling",
    "ThrottlingException",
    "RequestTimeout",
    "RequestLimitExceeded",
    "TooManyRequestsException",
}


class StorageError(RuntimeError):
    """Erreur de stockage non liée à l'indisponibilité du service."""


def is_retryable_s3_error(error: Exception) -> bool:
    """Erreurs réseau et 5xx / throttling : oui. NoSuchKey, AccessDenied... : non."""
    if isinstance(error, ClientError):
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        code = error.response.get("Error", {}).get("Code", "")
        return status >= 500 or code in THROTTLING_CODES
    return isinstance(error, (BotoCoreError, ConnectionError))


def ensure_bucket(client: Any, bucket: str) -> None:
    """Crée le bucket s'il n'existe pas. Avec retry (MinIO peut démarrer)."""

    def ensure() -> None:
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as error:
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status != 404:
                raise
            client.create_bucket(Bucket=bucket)
            logger.info("Bucket créé : %s", bucket)

    call_with_retry(
        ensure,
        operation=f"accès au bucket MinIO {bucket}",
        retry_on=S3_RETRY_ON,
        is_retryable=is_retryable_s3_error,
    )


def upload_file(client: Any, bucket: str, path: Path, key: str | None = None) -> str:
    """Envoie un fichier dans le bucket, puis vérifie qu'il est bien arrivé.

    La vérification compare la taille de l'objet stocké à celle du fichier local.
    Retourne la clé de l'objet (par défaut le nom du fichier).
    """
    object_key = key or path.name
    client.upload_file(str(path), bucket, object_key)
    stored_size = client.head_object(Bucket=bucket, Key=object_key)["ContentLength"]
    local_size = path.stat().st_size
    if stored_size != local_size:
        raise StorageError(
            f"Vérification de l'upload échouée pour {object_key} : "
            f"{stored_size} octets stockés, {local_size} attendus."
        )
    return object_key


def upload_files(client: Any, bucket: str, paths: Iterable[Path]) -> list[str]:
    return [upload_file(client, bucket, p) for p in paths]


def list_csv_keys(client: Any, bucket: str) -> list[str]:
    """Clés des fichiers .csv du bucket, triées. Avec retry."""

    def fetch() -> list[str]:
        keys: list[str] = []
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            keys.extend(
                obj["Key"]
                for obj in page.get("Contents", [])
                if obj["Key"].endswith(".csv")
            )
        return sorted(keys)

    return call_with_retry(
        fetch,
        operation=f"liste des fichiers MinIO (bucket {bucket})",
        retry_on=S3_RETRY_ON,
        is_retryable=is_retryable_s3_error,
    )


def read_object(client: Any, bucket: str, key: str) -> bytes:
    """Contenu d'un objet du bucket. Avec retry."""

    def fetch() -> bytes:
        body: bytes = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        return body

    return call_with_retry(
        fetch,
        operation=f"lecture MinIO de {key}",
        retry_on=S3_RETRY_ON,
        is_retryable=is_retryable_s3_error,
    )


def delete_bucket_with_content(client: Any, bucket: str) -> None:
    """Vide puis supprime un bucket (utilisé pour les buckets de test)."""
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            client.delete_object(Bucket=bucket, Key=obj["Key"])
    client.delete_bucket(Bucket=bucket)

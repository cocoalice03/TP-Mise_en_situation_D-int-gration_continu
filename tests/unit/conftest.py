from collections.abc import Iterator
from typing import Any

import pytest
from moto import mock_aws

BUCKET = "unit-bucket"


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pas d'attente réelle entre deux tentatives dans les tests unitaires."""
    monkeypatch.setenv("RETRY_DELAY_SECONDS", "0")
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "3")


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Client S3 simulé en mémoire (moto), avec un bucket vide."""
    monkeypatch.setenv("MINIO_ENDPOINT", "https://s3.amazonaws.com")
    monkeypatch.setenv("MINIO_ROOT_USER", "test-user")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "test-password")
    monkeypatch.setenv("MINIO_BUCKET", BUCKET)

    from src.storage import ensure_bucket, get_s3_client

    with mock_aws():
        client = get_s3_client()
        ensure_bucket(client, BUCKET)
        yield client

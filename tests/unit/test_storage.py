from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from src.retry import RetryExhaustedError
from src.storage import (
    StorageError,
    ensure_bucket,
    is_retryable_s3_error,
    list_csv_keys,
    read_object,
    upload_file,
    upload_files,
)
from tests.unit.conftest import BUCKET


def _client_error(code: str, status: int) -> ClientError:
    response: Any = {
        "Error": {"Code": code},
        "ResponseMetadata": {"HTTPStatusCode": status},
    }
    return ClientError(response, "op")


def test_ensure_bucket_creates_missing_bucket(s3: Any) -> None:
    ensure_bucket(s3, "new-bucket")
    names = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    assert "new-bucket" in names
    ensure_bucket(s3, "new-bucket")  # idempotent


def test_upload_is_verified_and_readable(s3: Any, tmp_path: Path) -> None:
    f = tmp_path / "a.csv"
    f.write_text("x,y\n1,2\n", encoding="utf-8")
    key = upload_file(s3, BUCKET, f)
    assert key == "a.csv"
    assert read_object(s3, BUCKET, "a.csv") == f.read_bytes()


def test_upload_detects_size_mismatch(s3: Any, tmp_path: Path) -> None:
    f = tmp_path / "a.csv"
    f.write_text("abc", encoding="utf-8")
    client = MagicMock()
    client.head_object.return_value = {"ContentLength": 1}
    with pytest.raises(StorageError, match="Vérification de l'upload"):
        upload_file(client, BUCKET, f)


def test_list_csv_keys_sorted_and_filtered(s3: Any, tmp_path: Path) -> None:
    for name in ["b.csv", "a.csv", "notes.txt"]:
        p = tmp_path / name
        p.write_text("x", encoding="utf-8")
    upload_files(s3, BUCKET, [tmp_path / "b.csv", tmp_path / "a.csv", tmp_path / "notes.txt"])
    assert list_csv_keys(s3, BUCKET) == ["a.csv", "b.csv"]


def test_read_object_retries_transient_error_then_succeeds() -> None:
    client = MagicMock()
    body = MagicMock()
    body.read.return_value = b"data"
    client.get_object.side_effect = [
        EndpointConnectionError(endpoint_url="http://localhost:9000"),
        _client_error("InternalError", 503),
        {"Body": body},
    ]
    assert read_object(client, BUCKET, "a.csv") == b"data"
    assert client.get_object.call_count == 3


def test_read_object_exhausted_gives_explicit_error() -> None:
    client = MagicMock()
    client.get_object.side_effect = EndpointConnectionError(endpoint_url="http://x")
    with pytest.raises(RetryExhaustedError, match="lecture MinIO de a.csv"):
        read_object(client, BUCKET, "a.csv")
    assert client.get_object.call_count == 3


def test_missing_key_is_permanent_and_not_retried() -> None:
    client = MagicMock()
    client.get_object.side_effect = _client_error("NoSuchKey", 404)
    with pytest.raises(ClientError):
        read_object(client, BUCKET, "absent.csv")
    assert client.get_object.call_count == 1


@pytest.mark.parametrize(
    "error,expected",
    [
        (_client_error("InternalError", 500), True),
        (_client_error("SlowDown", 503), True),
        (_client_error("NoSuchKey", 404), False),
        (_client_error("AccessDenied", 403), False),
        (EndpointConnectionError(endpoint_url="http://x"), True),
        (ConnectionError("reset"), True),
    ],
)
def test_is_retryable_s3_error(error: Exception, expected: bool) -> None:
    assert is_retryable_s3_error(error) is expected

"""Fixtures communes aux tests d'intégration (vrai MySQL + vrai MinIO).

Prérequis : `docker compose up -d --wait` avec le fichier .env rempli
(MYSQL_ROOT_PASSWORD est nécessaire pour créer la base de test).
Si MySQL ou MinIO n'est pas joignable, les tests sont ignorés.

Sécurité : les tests ne touchent JAMAIS aux données applicatives. Ils
travaillent dans une base dédiée `<MYSQL_DATABASE>_test` et un bucket dédié
`<MINIO_BUCKET>-test`, créés au début de la session et supprimés à la fin.
"""
import os
import re
from collections.abc import Iterator
from typing import Any

import pymysql
import pytest
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from pymysql.connections import Connection

from src.database import MissingConfigError, get_connection, init_db
from src.database.connection import ROOT_DIR
from src.storage import delete_bucket_with_content, get_s3_client

TEST_DB_SUFFIX = "_test"
TEST_BUCKET_SUFFIX = "-test"


def _root_connection() -> Connection:
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user="root",
        password=os.environ["MYSQL_ROOT_PASSWORD"],
        charset="utf8mb4",
    )


@pytest.fixture(scope="session")
def test_database() -> Iterator[str]:
    """Crée une base de test dédiée et redirige l'application vers elle."""
    load_dotenv(ROOT_DIR / ".env", override=False)
    try:
        app_db = os.environ["MYSQL_DATABASE"]
        app_user = os.environ["MYSQL_USER"]
        root = _root_connection()
    except KeyError as e:
        pytest.skip(f"Variable {e} manquante pour créer la base de test")
    except pymysql.err.OperationalError as e:
        pytest.skip(f"MySQL indisponible ({e})")

    name = app_db + TEST_DB_SUFFIX
    # Garde-fous : jamais d'opération destructive hors d'une base `*_test`
    assert name.endswith(TEST_DB_SUFFIX)
    assert re.fullmatch(r"[A-Za-z0-9_]+", name)
    assert re.fullmatch(r"[A-Za-z0-9_]+", app_user)

    with root.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS `{name}`")
        cur.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
        cur.execute(f"GRANT ALL PRIVILEGES ON `{name}`.* TO %s@'%%'", (app_user,))
    root.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MYSQL_DATABASE", name)  # run_pipeline() utilisera la base de test
        yield name

    with root.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS `{name}`")
    root.close()


@pytest.fixture
def conn(test_database: str) -> Iterator[Connection]:
    """Connexion à la base de test, avec des tables vides pour chaque test."""
    assert test_database.endswith(TEST_DB_SUFFIX)
    try:
        c = get_connection()
    except MissingConfigError as e:
        pytest.skip(str(e))
    except pymysql.err.OperationalError as e:
        pytest.skip(f"MySQL indisponible ({e})")
    init_db(c)
    with c.cursor() as cur:
        cur.execute("DELETE FROM transactions")
        cur.execute("DELETE FROM processed_files")
    c.commit()
    yield c
    c.close()


def fetch_all(conn: Connection, sql: str) -> list[Any]:
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = list(cur.fetchall())
    conn.commit()
    return rows


@pytest.fixture(scope="session")
def test_bucket() -> Iterator[str]:
    """Crée un bucket de test dédié et redirige l'application vers lui."""
    load_dotenv(ROOT_DIR / ".env", override=False)
    try:
        app_bucket = os.environ["MINIO_BUCKET"]
        client = get_s3_client()
    except KeyError as e:
        pytest.skip(f"Variable {e} manquante pour créer le bucket de test")
    except MissingConfigError as e:
        pytest.skip(str(e))
    try:
        existing = [b["Name"] for b in client.list_buckets()["Buckets"]]
    except (BotoCoreError, ClientError) as e:
        pytest.skip(f"MinIO indisponible ({e})")

    name = app_bucket + TEST_BUCKET_SUFFIX
    # Garde-fou : on ne vide / supprime jamais un bucket qui n'est pas `*-test`
    assert name.endswith(TEST_BUCKET_SUFFIX)
    if name in existing:
        delete_bucket_with_content(client, name)
    client.create_bucket(Bucket=name)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MINIO_BUCKET", name)  # run_pipeline() utilisera le bucket de test
        yield name

    delete_bucket_with_content(client, name)


@pytest.fixture
def s3(test_bucket: str) -> Iterator[Any]:
    """Client S3 réel ; le bucket de test est vidé avant chaque test."""
    assert test_bucket.endswith(TEST_BUCKET_SUFFIX)
    client = get_s3_client()
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=test_bucket):
        for obj in page.get("Contents", []):
            client.delete_object(Bucket=test_bucket, Key=obj["Key"])
    yield client

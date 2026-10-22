import os
from typing import Any

import boto3
from botocore.config import Config

from src.config import load_env, required_env


def get_bucket_name() -> str:
    return required_env("MINIO_BUCKET")


def get_s3_client() -> Any:
    """Client S3 (boto3) pointant sur MinIO, configuré par variables d'environnement.

    Identifiants (MINIO_ROOT_USER, MINIO_ROOT_PASSWORD) et MINIO_ENDPOINT n'ont
    pas de valeur par défaut. boto3 ne retente pas lui-même : le retry est
    géré par `src.retry` pour avoir un comportement et des messages uniques.
    """
    load_env()
    return boto3.client(
        "s3",
        endpoint_url=required_env("MINIO_ENDPOINT"),
        aws_access_key_id=required_env("MINIO_ROOT_USER"),
        aws_secret_access_key=required_env("MINIO_ROOT_PASSWORD"),
        region_name=os.environ.get("MINIO_REGION", "us-east-1"),
        config=Config(
            retries={"max_attempts": 0},
            connect_timeout=5,
            read_timeout=30,
            s3={"addressing_style": "path"},
        ),
    )

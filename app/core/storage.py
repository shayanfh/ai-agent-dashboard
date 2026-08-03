import asyncio
from functools import lru_cache
from typing import BinaryIO

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.core.config import Settings, settings


class ObjectStorage:
    def __init__(self, config: Settings) -> None:
        self._bucket = config.STORAGE_BUCKET
        client_options = {
            "aws_access_key_id": config.STORAGE_ACCESS_KEY,
            "aws_secret_access_key": config.STORAGE_SECRET_KEY,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self._client: BaseClient = boto3.client(
            "s3",
            endpoint_url=config.STORAGE_ENDPOINT,
            **client_options,
        )
        self._download_client: BaseClient = boto3.client(
            "s3",
            endpoint_url=config.STORAGE_PUBLIC_ENDPOINT or config.STORAGE_ENDPOINT,
            **client_options,
        )

    @property
    def bucket(self) -> str:
        return self._bucket

    async def upload(self, source: BinaryIO, *, key: str, content_type: str) -> str:
        source.seek(0)
        await asyncio.to_thread(
            self._client.upload_fileobj,
            source,
            self._bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return f"s3://{self._bucket}/{key}"

    async def presigned_download_url(self, *, key: str, expires_in: int) -> str:
        return await asyncio.to_thread(
            self._download_client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )


@lru_cache
def get_object_storage() -> ObjectStorage:
    return ObjectStorage(settings)

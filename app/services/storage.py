"""Where encrypted document bytes are kept. Files are encrypted by the app *before* they reach a backend, so the
backend only ever sees ciphertext. Keys are random names, never user input."""
from functools import lru_cache
from pathlib import Path

from ..config import settings


class LocalStorage:
    def __init__(self, directory: str):
        self.dir = Path(directory)

    def put(self, key: str, data: bytes) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / key).write_bytes(data)

    def get(self, key: str) -> bytes:
        return (self.dir / key).read_bytes()

    def delete(self, key: str) -> None:
        (self.dir / key).unlink(missing_ok=True)


class S3Storage:
    def __init__(self, bucket: str, prefix: str, region: str, endpoint_url: str):
        import boto3  # optional dependency: pip install -r requirements-s3.txt
        self.bucket, self.prefix = bucket, prefix
        self.client = boto3.client("s3", region_name=region or None, endpoint_url=endpoint_url or None)

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self.prefix + key, Body=data)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=self.prefix + key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self.prefix + key)  # deleting a missing key is not an error on S3


@lru_cache(maxsize=4)
def _build(backend: str, directory: str, bucket: str, prefix: str, region: str, endpoint: str):
    return S3Storage(bucket, prefix, region, endpoint) if backend == "s3" else LocalStorage(directory)


def get_storage():
    return _build(settings.storage_backend, settings.upload_dir, settings.s3_bucket, settings.s3_prefix, settings.s3_region, settings.s3_endpoint_url)

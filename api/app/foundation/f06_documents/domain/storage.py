"""AI-CONTEXT: Object-storage adapter seam for F6 (PRD §7.6, S3-compatible).

Documents live in object storage (MinIO in dev — already in the compose
topology on 9018/9019). The service depends on the ObjectStorage protocol, not
on any concrete client, so tests run against InMemoryObjectStorage with zero
infra and dev/prod swap in MinioObjectStorage. Keep the metadata (typed row,
extraction, expiry) in Postgres; only the bytes live here.
"""
from typing import Protocol


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class InMemoryObjectStorage:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        self._store[key] = data

    def get(self, key: str) -> bytes:
        return self._store[key]

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


class MinioObjectStorage:
    """AI-CONTEXT: Real dev/prod adapter over the MinIO S3 client. Lazy-imports
    `minio` so tests never pull it. Bucket + credentials come from settings.
    Wired when the first upload flow (M5 wallet / F6 consumers) lands.
    """

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str) -> None:
        from minio import Minio

        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)
        self._bucket = bucket
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        import io

        self._client.put_object(
            self._bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type or "application/octet-stream",
        )

    def get(self, key: str) -> bytes:
        response = self._client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, key: str) -> None:
        self._client.remove_object(self._bucket, key)


_default_storage: ObjectStorage = InMemoryObjectStorage()


def default_storage() -> ObjectStorage:
    return _default_storage


def set_default_storage(storage: ObjectStorage) -> None:
    global _default_storage
    _default_storage = storage

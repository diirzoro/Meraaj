"""Storage abstraction (S3-compatible ready). Local disk is a DEV-ONLY default and is
NOT a final production solution — set STORAGE_BACKEND=s3 with real credentials at deploy.
Files are private (no public URLs); reads go through an authorized app endpoint."""
import os
import uuid
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Tuple

MAX_FILE_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg", "image/jpg",
                "image/webp", "image/heic", "image/heif"}


class Storage(ABC):
    @abstractmethod
    async def put(self, data: bytes, content_type: str, prefix: str = "") -> str: ...

    @abstractmethod
    async def get(self, key: str) -> Tuple[bytes, str]: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    def url(self, key: str):
        return None


class LocalStorage(Storage):
    def __init__(self):
        self.root = Path(os.environ.get("LOCAL_STORAGE_DIR", str(Path(__file__).parent / "_storage")))
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, data: bytes, content_type: str, prefix: str = "") -> str:
        rand = uuid.uuid4().hex
        key = f"{prefix.strip('/')}/{rand}" if prefix else rand
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        (self.root / (key + ".ct")).write_text(content_type or "application/octet-stream")
        return key

    async def get(self, key: str) -> Tuple[bytes, str]:
        p = self.root / key
        if not p.exists():
            raise FileNotFoundError(key)
        ct_p = self.root / (key + ".ct")
        ct = ct_p.read_text() if ct_p.exists() else "application/octet-stream"
        return p.read_bytes(), ct

    async def delete(self, key: str) -> None:
        for f in (self.root / key, self.root / (key + ".ct")):
            try:
                f.unlink()
            except FileNotFoundError:
                pass


class S3Storage(Storage):
    """S3-compatible placeholder. Wire boto3/aioboto3 + env credentials at deploy time.
    Intentionally does NOT initialize a client without credentials."""
    def __init__(self):
        self.bucket = os.environ.get("S3_BUCKET")

    async def put(self, data: bytes, content_type: str, prefix: str = "") -> str:
        raise NotImplementedError("S3 storage not configured")

    async def get(self, key: str) -> Tuple[bytes, str]:
        raise NotImplementedError("S3 storage not configured")

    async def delete(self, key: str) -> None:
        raise NotImplementedError("S3 storage not configured")

    def url(self, key: str):
        raise NotImplementedError("S3 storage not configured")


_backend = None


def get_storage() -> Storage:
    global _backend
    if _backend is None:
        kind = os.environ.get("STORAGE_BACKEND", "local").lower()
        _backend = S3Storage() if kind == "s3" else LocalStorage()
    return _backend

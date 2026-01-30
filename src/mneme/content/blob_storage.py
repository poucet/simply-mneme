"""Filesystem BlobStore — content-addressable blob storage.

Implements BlobStore using sharded local filesystem storage with SHA-256
content hashes. Files are stored at: {storage_root}/{hash[:2]}/{hash}{ext}

For S3 or other backends, implement the BlobStore protocol directly.
"""

import hashlib
from pathlib import Path
from typing import Optional

import aiofiles
import aiofiles.os

from .protocol import BlobStore


# Extension mapping for common MIME types
_MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "audio/wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "application/pdf": ".pdf",
}


def compute_hash(data: bytes) -> str:
    """Compute SHA-256 hash of data."""
    return hashlib.sha256(data).hexdigest()


def extension_for_mime(mime_type: str) -> str:
    """Get file extension for a MIME type."""
    return _MIME_TO_EXT.get(mime_type, ".bin")


class BlobStorage(BlobStore):
    """Content-addressable blob storage with sharding.

    Files are stored using their SHA-256 hash as the filename,
    sharded into subdirectories by the first 2 characters of the hash.

    Example: blob with hash "7f8a9b..." and mime "image/png"
             is stored at "7f/7f8a9b....png"
    """

    def __init__(self, storage_root: Path) -> None:
        self.storage_root = Path(storage_root)

    async def ensure_initialized(self) -> None:
        """Ensure storage directory exists."""
        await aiofiles.os.makedirs(self.storage_root, exist_ok=True)

    def relative_path(self, content_hash: str, mime_type: str) -> str:
        """Get the relative storage path for a content hash."""
        shard = content_hash[:2]
        ext = extension_for_mime(mime_type)
        return f"{shard}/{content_hash}{ext}"

    def absolute_path(self, relative_path: str) -> Path:
        """Get absolute path from relative path."""
        return self.storage_root / relative_path

    async def store(self, data: bytes, mime_type: str) -> tuple[str, str]:
        """Store blob data, returning (content_hash, relative_path).

        Deduplicates: if a blob with the same hash already exists,
        this is a no-op and returns the existing path.
        """
        content_hash = compute_hash(data)
        rel_path = self.relative_path(content_hash, mime_type)
        abs_path = self.absolute_path(rel_path)

        shard_dir = abs_path.parent
        await aiofiles.os.makedirs(shard_dir, exist_ok=True)

        if not await self.exists(content_hash, mime_type):
            async with aiofiles.open(abs_path, "wb") as f:
                await f.write(data)

        return content_hash, rel_path

    async def retrieve(self, relative_path: str) -> Optional[bytes]:
        """Retrieve blob data by relative path. Returns None if missing."""
        abs_path = self.absolute_path(relative_path)
        try:
            async with aiofiles.open(abs_path, "rb") as f:
                return await f.read()
        except FileNotFoundError:
            return None

    async def retrieve_by_hash(self, content_hash: str, mime_type: str) -> Optional[bytes]:
        """Retrieve blob data by content hash."""
        rel_path = self.relative_path(content_hash, mime_type)
        return await self.retrieve(rel_path)

    async def exists(self, content_hash: str, mime_type: str) -> bool:
        """Check if a blob exists in storage."""
        rel_path = self.relative_path(content_hash, mime_type)
        abs_path = self.absolute_path(rel_path)
        try:
            await aiofiles.os.stat(str(abs_path))
            return True
        except FileNotFoundError:
            return False

    async def delete(self, relative_path: str) -> bool:
        """Delete a blob from storage. Returns True if deleted."""
        abs_path = self.absolute_path(relative_path)
        try:
            await aiofiles.os.remove(str(abs_path))
            # Try to remove empty shard directory
            try:
                await aiofiles.os.rmdir(str(abs_path.parent))
            except OSError:
                pass  # Directory not empty
            return True
        except FileNotFoundError:
            return False

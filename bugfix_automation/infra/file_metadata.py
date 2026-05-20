from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from typing import Any


def file_metadata(path: Path, original_name: str = "") -> dict[str, Any]:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "original_name": original_name or path.name,
        "stored_name": path.name,
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "sha256": digest.hexdigest(),
    }

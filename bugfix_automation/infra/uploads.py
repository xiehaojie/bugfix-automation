from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import zipfile


def safe_upload_name(original_name: str) -> str:
    stem = Path(original_name).stem or "bugs"
    safe_stem = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", stem).strip(".-") or "bugs"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"{safe_stem}-{stamp}.xlsx"


def validate_xlsx(path: Path, missing_message: str = "文件不存在") -> None:
    if not path.is_file():
        raise ValueError(f"{missing_message}: {path}")
    if path.suffix.lower() != ".xlsx":
        raise ValueError("只支持 .xlsx 文件")
    if not zipfile.is_zipfile(path):
        raise ValueError("选择的 xlsx 文件不完整或不是有效的 Excel 文件")


def validate_uploaded_xlsx(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        path.unlink(missing_ok=True)
        raise ValueError("上传的 xlsx 文件不完整或不是有效的 Excel 文件；请重新上传原始 .xlsx 文件")

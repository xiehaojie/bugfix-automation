from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SheetRef:
    provider: str
    source_url: str
    workbook_id: str
    sheet_id: str = ""
    title: str = ""


@dataclass(frozen=True)
class SheetMeta:
    sheet_id: str
    title: str


@dataclass(frozen=True)
class SheetTable:
    ref: SheetRef
    range_address: str
    headers: list[str]
    rows: list[dict[str, str]]


class OnlineSheetProvider(Protocol):
    key: str
    label: str

    def parse_url(self, url: str) -> SheetRef:
        ...

    def read_range(self, ref: SheetRef, range_address: str) -> SheetTable:
        ...


class OnlineSheetError(RuntimeError):
    pass


class OnlineSheetAuthError(OnlineSheetError):
    pass


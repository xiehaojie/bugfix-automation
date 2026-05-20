from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from bugfix_automation.api.schemas import ExcelPathRequest
from bugfix_automation.application.excel_service import get_excel_columns, select_excel_path, upload_excel_bytes

router = APIRouter()


@router.post("/api/excel/upload")
async def post_excel_upload(file: UploadFile = File(...)):
    return upload_excel_bytes(file.filename or "", await file.read())


@router.post("/api/excel/select-path")
def post_excel_select_path(payload: ExcelPathRequest):
    return select_excel_path(payload.path)


@router.get("/api/excel/columns")
def get_columns():
    return get_excel_columns()

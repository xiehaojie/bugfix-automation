from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from bugfix_automation.server.api.dependencies import get_config
from bugfix_automation.server.api.schemas import ExcelAdapterAnalyzeRequest, ExcelAdapterSaveRequest, ExcelPathRequest
from bugfix_automation.services.excel_adapter_service import analyze_excel_adapter, save_excel_adapter
from bugfix_automation.services.excel_service import get_excel_columns, select_excel_path, upload_excel_bytes
from bugfix_automation.config import Config

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


@router.post("/api/excel/adapter/analyze")
async def post_excel_adapter_analyze(payload: ExcelAdapterAnalyzeRequest | None = None, config: Config = Depends(get_config)):
    return await analyze_excel_adapter(config, cli_tool=payload.cli_tool if payload else "")


@router.post("/api/excel/adapter/save")
def post_excel_adapter_save(payload: ExcelAdapterSaveRequest, config: Config = Depends(get_config)):
    return save_excel_adapter(config, payload.adapter)

# -*- coding: utf-8 -*-
"""
===================================
股票資料介面
===================================

職責：
1. POST /api/v1/stocks/extract-from-image 從圖片提取股票程式碼
2. POST /api/v1/stocks/parse-import 解析 CSV/Excel/剪貼簿
3. GET /api/v1/stocks/{code}/quote 實時行情介面
4. GET /api/v1/stocks/{code}/history 歷史行情介面
"""

import logging
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from api.v1.schemas.stocks import (
    ExtractFromImageResponse,
    ExtractItem,
    KLineData,
    StockHistoryResponse,
    StockQuote,
)
from api.v1.schemas.common import ErrorResponse
from src.services.image_stock_extractor import (
    ALLOWED_MIME,
    MAX_SIZE_BYTES,
    extract_stock_codes_from_image,
)
from src.services.import_parser import (
    MAX_FILE_BYTES,
    parse_import_from_bytes,
    parse_import_from_text,
)
from src.services.stock_service import StockService

logger = logging.getLogger(__name__)

router = APIRouter()

# 須在 /{stock_code} 路由之前定義
ALLOWED_MIME_STR = ", ".join(ALLOWED_MIME)


@router.post(
    "/extract-from-image",
    response_model=ExtractFromImageResponse,
    responses={
        200: {"description": "提取的股票程式碼"},
        400: {"description": "圖片無效", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="從圖片提取股票程式碼",
    description="上傳截圖/圖片，透過 Vision LLM 提取股票程式碼。支援 JPEG、PNG、WebP、GIF，最大 5MB。",
)
def extract_from_image(
    file: Optional[UploadFile] = File(None, description="圖片檔案（表單欄位名 file）"),
    include_raw: bool = Query(False, description="是否在結果中包含原始 LLM 響應"),
) -> ExtractFromImageResponse:
    """
    從上傳的圖片中提取股票程式碼（使用 Vision LLM）。

    表單欄位請使用 file 上傳圖片。優先順序：Gemini / Anthropic / OpenAI（首個可用）。
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": "未提供檔案，請使用表單欄位 file 上傳圖片"},
        )

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_type",
                "message": f"不支援的型別: {content_type}。允許: {ALLOWED_MIME_STR}",
            },
        )

    try:
        # 先讀取限定大小，再檢查是否還有剩餘（語義清晰：超出則拒絕）
        data = file.file.read(MAX_SIZE_BYTES)
        if file.file.read(1):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "file_too_large",
                    "message": f"圖片超過 {MAX_SIZE_BYTES // (1024 * 1024)}MB 限制",
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"讀取上傳檔案失敗: {e}")
        raise HTTPException(
            status_code=400,
            detail={"error": "read_failed", "message": "讀取上傳檔案失敗"},
        )

    try:
        items, raw_text = extract_stock_codes_from_image(data, content_type)
        extract_items = [
            ExtractItem(code=code, name=name, confidence=conf) for code, name, conf in items
        ]
        codes = [i.code for i in extract_items]
        return ExtractFromImageResponse(
            codes=codes,
            items=extract_items,
            raw_text=raw_text if include_raw else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "extract_failed", "message": str(e)})
    except Exception as e:
        logger.error(f"圖片提取失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "圖片提取失敗"},
        )


@router.post(
    "/parse-import",
    response_model=ExtractFromImageResponse,
    responses={
        200: {"description": "解析結果"},
        400: {"description": "未提供資料或解析失敗", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="解析 CSV/Excel/剪貼簿",
    description="上傳 CSV/Excel 檔案或貼上文字，自動解析股票程式碼。檔案上限 2MB，文字上限 100KB。",
)
async def parse_import(request: Request) -> ExtractFromImageResponse:
    """
    解析 CSV/Excel 檔案或剪貼簿文字。

    - multipart/form-data + file: 上傳檔案
    - application/json + {"text": "..."}: 貼上文字
    - 優先使用 file，若同時提供則忽略 text
    """
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception as e:
            logger.warning("[parse_import] JSON parse failed: %s", e)
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_json", "message": f"JSON 解析失敗: {e}"},
            )
        text = body.get("text") if isinstance(body, dict) else None
        if not text or not isinstance(text, str):
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_request", "message": "未提供 text，請使用 {\"text\": \"...\"}"},
            )
        try:
            items = parse_import_from_text(text)
        except ValueError as e:
            text_bytes = len(text.encode("utf-8"))
            logger.warning(
                "[parse_import] parse_import_from_text failed: text_bytes=%d, error=%s",
                text_bytes,
                e,
            )
            raise HTTPException(status_code=400, detail={"error": "parse_failed", "message": str(e)})
    elif "multipart" in content_type:
        form = await request.form()
        file = form.get("file")
        if not file or not hasattr(file, "read"):
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_request", "message": "未提供檔案，請使用表單欄位 file"},
            )
        file_size = getattr(file, "size", None)
        if isinstance(file_size, int) and file_size > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "file_too_large",
                    "message": f"檔案超過 {MAX_FILE_BYTES // (1024 * 1024)}MB 限制",
                },
            )
        try:
            data = file.file.read(MAX_FILE_BYTES)
            if file.file.read(1):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "file_too_large",
                        "message": f"檔案超過 {MAX_FILE_BYTES // (1024 * 1024)}MB 限制",
                    },
                )
        except HTTPException:
            raise
        except Exception as e:
            filename = getattr(file, "filename", None) or ""
            size = getattr(file, "size", None)
            logger.warning(
                "[parse_import] file read failed: filename=%r, size=%s, error=%s",
                filename,
                size,
                e,
            )
            raise HTTPException(
                status_code=400,
                detail={"error": "read_failed", "message": "讀取檔案失敗"},
            )
        filename = getattr(file, "filename", None) or ""
        try:
            items = parse_import_from_bytes(data, filename=filename)
        except ValueError as e:
            ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            logger.warning(
                "[parse_import] parse_import_from_bytes failed: filename=%r, ext=%r, bytes=%d, error=%s",
                filename,
                ext,
                len(data),
                e,
            )
            raise HTTPException(status_code=400, detail={"error": "parse_failed", "message": str(e)})
    else:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_request",
                "message": "請使用 multipart/form-data 上傳檔案，或 application/json 提交 {\"text\": \"...\"}",
            },
        )

    extract_items = [
        ExtractItem(code=code, name=name, confidence=conf)
        for code, name, conf in items
    ]
    codes = list(dict.fromkeys(i.code for i in extract_items if i.code))
    return ExtractFromImageResponse(codes=codes, items=extract_items, raw_text=None)


@router.get(
    "/{stock_code}/quote",
    response_model=StockQuote,
    responses={
        200: {"description": "行情資料"},
        404: {"description": "股票不存在", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取股票實時行情",
    description="獲取指定股票的最新行情資料"
)
def get_stock_quote(stock_code: str) -> StockQuote:
    """
    獲取股票實時行情
    
    獲取指定股票的最新行情資料
    
    Args:
        stock_code: 股票程式碼（如 600519、00700、AAPL）
        
    Returns:
        StockQuote: 實時行情資料
        
    Raises:
        HTTPException: 404 - 股票不存在
    """
    try:
        service = StockService()
        
        # 使用 def 而非 async def，FastAPI 自動線上程池中執行
        result = service.get_realtime_quote(stock_code)
        
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"未找到股票 {stock_code} 的行情資料"
                }
            )
        
        return StockQuote(
            stock_code=result.get("stock_code", stock_code),
            stock_name=result.get("stock_name"),
            current_price=result.get("current_price", 0.0),
            change=result.get("change"),
            change_percent=result.get("change_percent"),
            open=result.get("open"),
            high=result.get("high"),
            low=result.get("low"),
            prev_close=result.get("prev_close"),
            volume=result.get("volume"),
            amount=result.get("amount"),
            update_time=result.get("update_time")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"獲取實時行情失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"獲取實時行情失敗: {str(e)}"
            }
        )


@router.get(
    "/{stock_code}/history",
    response_model=StockHistoryResponse,
    responses={
        200: {"description": "歷史行情資料"},
        422: {"description": "不支援的週期引數", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取股票歷史行情",
    description="獲取指定股票的歷史 K 線資料"
)
def get_stock_history(
    stock_code: str,
    period: str = Query("daily", description="K 線週期", pattern="^(daily|weekly|monthly)$"),
    days: int = Query(30, ge=1, le=365, description="獲取天數")
) -> StockHistoryResponse:
    """
    獲取股票歷史行情
    
    獲取指定股票的歷史 K 線資料
    
    Args:
        stock_code: 股票程式碼
        period: K 線週期 (daily/weekly/monthly)
        days: 獲取天數
        
    Returns:
        StockHistoryResponse: 歷史行情資料
    """
    try:
        service = StockService()
        
        # 使用 def 而非 async def，FastAPI 自動線上程池中執行
        result = service.get_history_data(
            stock_code=stock_code,
            period=period,
            days=days
        )
        
        # 轉換為響應模型
        data = [
            KLineData(
                date=item.get("date"),
                open=item.get("open"),
                high=item.get("high"),
                low=item.get("low"),
                close=item.get("close"),
                volume=item.get("volume"),
                amount=item.get("amount"),
                change_percent=item.get("change_percent")
            )
            for item in result.get("data", [])
        ]
        
        return StockHistoryResponse(
            stock_code=stock_code,
            stock_name=result.get("stock_name"),
            period=period,
            data=data
        )
    
    except ValueError as e:
        # period 引數不支援的錯誤（如 weekly/monthly）
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_period",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"獲取歷史行情失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"獲取歷史行情失敗: {str(e)}"
            }
        )

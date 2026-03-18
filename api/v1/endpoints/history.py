# -*- coding: utf-8 -*-
"""
===================================
歷史記錄介面
===================================

職責：
1. 提供 GET /api/v1/history 歷史列表查詢介面
2. 提供 GET /api/v1/history/{query_id} 歷史詳情查詢介面
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends, Body

from api.deps import get_database_manager
from api.v1.schemas.history import (
    HistoryListResponse,
    HistoryItem,
    DeleteHistoryRequest,
    DeleteHistoryResponse,
    NewsIntelItem,
    NewsIntelResponse,
    AnalysisReport,
    ReportMeta,
    ReportSummary,
    ReportStrategy,
    ReportDetails,
    MarkdownReportResponse,
)
from api.v1.schemas.common import ErrorResponse
from src.storage import DatabaseManager
from src.services.history_service import HistoryService, MarkdownReportGenerationError
from src.utils.data_processing import normalize_model_used, extract_fundamental_detail_fields

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=HistoryListResponse,
    responses={
        200: {"description": "歷史記錄列表"},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取歷史分析列表",
    description="分頁獲取歷史分析記錄摘要，支援按股票程式碼和日期範圍篩選"
)
def get_history_list(
    stock_code: Optional[str] = Query(None, description="股票程式碼篩選"),
    start_date: Optional[str] = Query(None, description="開始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="頁碼（從 1 開始）"),
    limit: int = Query(20, ge=1, le=100, description="每頁數量"),
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> HistoryListResponse:
    """
    獲取歷史分析列表
    
    分頁獲取歷史分析記錄摘要，支援按股票程式碼和日期範圍篩選
    
    Args:
        stock_code: 股票程式碼篩選
        start_date: 開始日期
        end_date: 結束日期
        page: 頁碼
        limit: 每頁數量
        db_manager: 資料庫管理器依賴
        
    Returns:
        HistoryListResponse: 歷史記錄列表
    """
    try:
        service = HistoryService(db_manager)
        
        # 使用 def 而非 async def，FastAPI 自動線上程池中執行
        result = service.get_history_list(
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            page=page,
            limit=limit
        )
        
        # 轉換為響應模型
        items = [
            HistoryItem(
                id=item.get("id"),
                query_id=item.get("query_id", ""),
                stock_code=item.get("stock_code", ""),
                stock_name=item.get("stock_name"),
                report_type=item.get("report_type"),
                sentiment_score=item.get("sentiment_score"),
                operation_advice=item.get("operation_advice"),
                created_at=item.get("created_at")
            )
            for item in result.get("items", [])
        ]
        
        return HistoryListResponse(
            total=result.get("total", 0),
            page=page,
            limit=limit,
            items=items
        )
        
    except Exception as e:
        logger.error(f"查詢歷史列表失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"查詢歷史列表失敗: {str(e)}"
            }
        )


@router.delete(
    "",
    response_model=DeleteHistoryResponse,
    responses={
        200: {"description": "刪除成功"},
        400: {"description": "請求引數錯誤", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="刪除歷史分析記錄",
    description="按歷史記錄主鍵 ID 批次刪除分析歷史"
)
def delete_history_records(
    request: DeleteHistoryRequest = Body(...),
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> DeleteHistoryResponse:
    """
    按主鍵 ID 批次刪除歷史分析記錄。
    """
    record_ids = sorted({record_id for record_id in request.record_ids if record_id is not None})
    if not record_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_request",
                "message": "record_ids 不能為空"
            }
        )

    try:
        service = HistoryService(db_manager)
        deleted = service.delete_history_records(record_ids)
        return DeleteHistoryResponse(deleted=deleted)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除歷史記錄失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"刪除歷史記錄失敗: {str(e)}"
            }
        )


@router.get(
    "/{record_id}",
    response_model=AnalysisReport,
    responses={
        200: {"description": "報告詳情"},
        404: {"description": "報告不存在", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取歷史報告詳情",
    description="根據分析歷史記錄 ID 或 query_id 獲取完整的歷史分析報告"
)
def get_history_detail(
    record_id: str,
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> AnalysisReport:
    """
    獲取歷史報告詳情
    
    根據分析歷史記錄主鍵 ID 或 query_id 獲取完整的歷史分析報告。
    優先嚐試按主鍵 ID（整數）查詢，若引數不是合法整數則按 query_id 查詢。
    
    Args:
        record_id: 分析歷史記錄主鍵 ID（整數）或 query_id（字串）
        db_manager: 資料庫管理器依賴
        
    Returns:
        AnalysisReport: 完整分析報告
        
    Raises:
        HTTPException: 404 - 報告不存在
    """
    try:
        service = HistoryService(db_manager)
        
        # Try integer ID first, fall back to query_id string lookup
        result = service.resolve_and_get_detail(record_id)
        
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"未找到 id/query_id={record_id} 的分析記錄"
                }
            )
        
        # 從 context_snapshot 中提取價格資訊
        current_price = None
        change_pct = None
        context_snapshot = result.get("context_snapshot")
        if context_snapshot and isinstance(context_snapshot, dict):
            # 嘗試從 enhanced_context.realtime 獲取
            enhanced_context = context_snapshot.get("enhanced_context") or {}
            realtime = enhanced_context.get("realtime") or {}
            current_price = realtime.get("price")
            change_pct = realtime.get("change_pct") or realtime.get("change_60d")
            
            # 也嘗試從 realtime_quote_raw 獲取
            if current_price is None:
                realtime_quote_raw = context_snapshot.get("realtime_quote_raw") or {}
                current_price = realtime_quote_raw.get("price")
                change_pct = change_pct or realtime_quote_raw.get("change_pct") or realtime_quote_raw.get("pct_chg")
        
        # 構建響應模型
        meta = ReportMeta(
            id=result.get("id"),
            query_id=result.get("query_id", ""),
            stock_code=result.get("stock_code", ""),
            stock_name=result.get("stock_name"),
            report_type=result.get("report_type"),
            created_at=result.get("created_at"),
            current_price=current_price,
            change_pct=change_pct,
            model_used=normalize_model_used(result.get("model_used"))
        )
        
        summary = ReportSummary(
            analysis_summary=result.get("analysis_summary"),
            operation_advice=result.get("operation_advice"),
            trend_prediction=result.get("trend_prediction"),
            sentiment_score=result.get("sentiment_score"),
            sentiment_label=result.get("sentiment_label")
        )
        
        strategy = ReportStrategy(
            ideal_buy=result.get("ideal_buy"),
            secondary_buy=result.get("secondary_buy"),
            stop_loss=result.get("stop_loss"),
            take_profit=result.get("take_profit")
        )
        
        fallback_fundamental = db_manager.get_latest_fundamental_snapshot(
            query_id=result.get("query_id", ""),
            code=result.get("stock_code", ""),
        )
        extracted_fundamental = extract_fundamental_detail_fields(
            context_snapshot=result.get("context_snapshot"),
            fallback_fundamental_payload=fallback_fundamental,
        )

        details = ReportDetails(
            news_content=result.get("news_content"),
            raw_result=result.get("raw_result"),
            context_snapshot=result.get("context_snapshot"),
            financial_report=extracted_fundamental.get("financial_report"),
            dividend_metrics=extracted_fundamental.get("dividend_metrics"),
        )
        
        return AnalysisReport(
            meta=meta,
            summary=summary,
            strategy=strategy,
            details=details
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查詢歷史詳情失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"查詢歷史詳情失敗: {str(e)}"
            }
        )


@router.get(
    "/{record_id}/news",
    response_model=NewsIntelResponse,
    responses={
        200: {"description": "新聞情報列表"},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取歷史報告關聯新聞",
    description="根據分析歷史記錄 ID 獲取關聯的新聞情報列表（為空也返回 200）"
)
def get_history_news(
    record_id: str,
    limit: int = Query(20, ge=1, le=100, description="返回數量限制"),
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> NewsIntelResponse:
    """
    獲取歷史報告關聯新聞

    根據分析歷史記錄 ID 或 query_id 獲取關聯的新聞情報列表。
    在內部完成 record_id → query_id 的解析。

    Args:
        record_id: 分析歷史記錄主鍵 ID（整數）或 query_id（字串）
        limit: 返回數量限制
        db_manager: 資料庫管理器依賴

    Returns:
        NewsIntelResponse: 新聞情報列表
    """
    try:
        service = HistoryService(db_manager)
        items = service.resolve_and_get_news(record_id=record_id, limit=limit)

        response_items = [
            NewsIntelItem(
                title=item.get("title", ""),
                snippet=item.get("snippet"),
                url=item.get("url", "")
            )
            for item in items
        ]

        return NewsIntelResponse(
            total=len(response_items),
            items=response_items
        )

    except Exception as e:
        logger.error(f"查詢新聞情報失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"查詢新聞情報失敗: {str(e)}"
            }
        )


@router.get(
    "/{record_id}/markdown",
    response_model=MarkdownReportResponse,
    responses={
        200: {"description": "Markdown 格式報告"},
        404: {"description": "報告不存在", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取歷史報告 Markdown 格式",
    description="根據分析歷史記錄 ID 獲取 Markdown 格式的完整分析報告"
)
def get_history_markdown(
    record_id: str,
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> MarkdownReportResponse:
    """
    獲取歷史報告的 Markdown 格式內容

    根據分析歷史記錄 ID 或 query_id 生成與推送通知格式一致的 Markdown 報告。

    Args:
        record_id: 分析歷史記錄主鍵 ID（整數）或 query_id（字串）
        db_manager: 資料庫管理器依賴

    Returns:
        MarkdownReportResponse: Markdown 格式的完整報告

    Raises:
        HTTPException: 404 - 報告不存在
        HTTPException: 500 - 報告生成失敗（伺服器內部錯誤）
    """
    service = HistoryService(db_manager)

    try:
        markdown_content = service.get_markdown_report(record_id)
    except MarkdownReportGenerationError as e:
        logger.error(f"Markdown report generation failed for {record_id}: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "generation_failed",
                "message": f"生成 Markdown 報告失敗: {e.message}"
            }
        )
    except Exception as e:
        logger.error(f"獲取 Markdown 報告失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"獲取 Markdown 報告失敗: {str(e)}"
            }
        )

    if markdown_content is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"未找到 id/query_id={record_id} 的分析記錄"
            }
        )

    return MarkdownReportResponse(content=markdown_content)

# -*- coding: utf-8 -*-
"""Backtest endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_database_manager
from api.v1.schemas.backtest import (
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestResultItem,
    BacktestResultsResponse,
    PerformanceMetrics,
)
from api.v1.schemas.common import ErrorResponse
from src.services.backtest_service import BacktestService
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/run",
    response_model=BacktestRunResponse,
    responses={
        200: {"description": "回測執行完成"},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="觸發回測",
    description="對歷史分析記錄進行回測評估，並寫入 backtest_results/backtest_summaries",
)
def run_backtest(
    request: BacktestRunRequest,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> BacktestRunResponse:
    try:
        service = BacktestService(db_manager)
        stats = service.run_backtest(
            code=request.code,
            force=request.force,
            eval_window_days=request.eval_window_days,
            min_age_days=request.min_age_days,
            limit=request.limit,
        )
        return BacktestRunResponse(**stats)
    except Exception as exc:
        logger.error(f"回測執行失敗: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"回測執行失敗: {str(exc)}"},
        )


@router.get(
    "/results",
    response_model=BacktestResultsResponse,
    responses={
        200: {"description": "回測結果列表"},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取回測結果",
    description="分頁獲取回測結果，支援按股票程式碼過濾",
)
def get_backtest_results(
    code: Optional[str] = Query(None, description="股票程式碼篩選"),
    eval_window_days: Optional[int] = Query(None, ge=1, le=120, description="評估視窗過濾"),
    page: int = Query(1, ge=1, description="頁碼"),
    limit: int = Query(20, ge=1, le=200, description="每頁數量"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> BacktestResultsResponse:
    try:
        service = BacktestService(db_manager)
        data = service.get_recent_evaluations(code=code, eval_window_days=eval_window_days, limit=limit, page=page)
        items = [BacktestResultItem(**item) for item in data.get("items", [])]
        return BacktestResultsResponse(
            total=int(data.get("total", 0)),
            page=page,
            limit=limit,
            items=items,
        )
    except Exception as exc:
        logger.error(f"查詢回測結果失敗: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"查詢回測結果失敗: {str(exc)}"},
        )


@router.get(
    "/performance",
    response_model=PerformanceMetrics,
    responses={
        200: {"description": "整體回測表現"},
        404: {"description": "無回測彙總", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取整體回測表現",
)
def get_overall_performance(
    eval_window_days: Optional[int] = Query(None, ge=1, le=120, description="評估視窗過濾"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> PerformanceMetrics:
    try:
        service = BacktestService(db_manager)
        summary = service.get_summary(scope="overall", code=None, eval_window_days=eval_window_days)
        if summary is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "未找到整體回測彙總"},
            )
        return PerformanceMetrics(**summary)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"查詢整體表現失敗: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"查詢整體表現失敗: {str(exc)}"},
        )


@router.get(
    "/performance/{code}",
    response_model=PerformanceMetrics,
    responses={
        200: {"description": "單股回測表現"},
        404: {"description": "無回測彙總", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取單股回測表現",
)
def get_stock_performance(
    code: str,
    eval_window_days: Optional[int] = Query(None, ge=1, le=120, description="評估視窗過濾"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> PerformanceMetrics:
    try:
        service = BacktestService(db_manager)
        summary = service.get_summary(scope="stock", code=code, eval_window_days=eval_window_days)
        if summary is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"未找到 {code} 的回測彙總"},
            )
        return PerformanceMetrics(**summary)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"查詢單股表現失敗: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"查詢單股表現失敗: {str(exc)}"},
        )


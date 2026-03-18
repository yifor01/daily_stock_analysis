# -*- coding: utf-8 -*-
"""
===================================
股票分析介面
===================================

職責：
1. 提供 POST /api/v1/analysis/analyze 觸發分析介面
2. 提供 GET /api/v1/analysis/status/{task_id} 查詢任務狀態介面
3. 提供 GET /api/v1/analysis/tasks 獲取任務列表介面
4. 提供 GET /api/v1/analysis/tasks/stream SSE 實時推送介面

特性：
- 非同步任務佇列：分析任務非同步執行，不阻塞請求
- 防重複提交：相同股票程式碼正在分析時返回 409
- SSE 實時推送：任務狀態變化實時通知前端
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Union, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse

from api.deps import get_config_dep
from api.v1.schemas.analysis import (
    AnalyzeRequest,
    AnalysisResultResponse,
    TaskAccepted,
    BatchTaskAcceptedResponse,
    BatchTaskAcceptedItem,
    BatchDuplicateTaskItem,
    TaskStatus,
    TaskInfo,
    TaskListResponse,
    DuplicateTaskErrorResponse,
)
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.history import (
    AnalysisReport,
    ReportMeta,
    ReportSummary,
    ReportStrategy,
    ReportDetails,
)
from data_provider.base import canonical_stock_code
from src.config import Config
from src.services.task_queue import (
    get_task_queue,
    DuplicateTaskError,
    TaskStatus as TaskStatusEnum,
)
from src.utils.data_processing import (
    normalize_model_used,
    parse_json_field,
    extract_fundamental_detail_fields,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# POST /analyze - 觸發股票分析
# ============================================================

@router.post(
    "/analyze",
    response_model=AnalysisResultResponse,
    responses={
        200: {"description": "分析完成（同步模式）", "model": AnalysisResultResponse},
        202: {
            "description": "分析任務已接受（非同步模式）",
            "model": Union[TaskAccepted, BatchTaskAcceptedResponse],
        },
        400: {"description": "請求引數錯誤", "model": ErrorResponse},
        409: {"description": "股票正在分析中，拒絕重複提交", "model": DuplicateTaskErrorResponse},
        500: {"description": "分析失敗", "model": ErrorResponse},
    },
    summary="觸發股票分析",
    description="啟動 AI 智慧分析任務，支援同步和非同步模式。非同步模式下相同股票程式碼不允許重複提交。"
)
def trigger_analysis(
        request: AnalyzeRequest,
        config: Config = Depends(get_config_dep)
) -> Union[AnalysisResultResponse, JSONResponse]:
    """
    觸發股票分析
    
    啟動 AI 智慧分析任務，支援單隻或多隻股票批次分析
    
    流程：
    1. 校驗請求引數
    2. 非同步模式：檢查重複 -> 提交任務佇列 -> 返回 202
    3. 同步模式：直接執行分析 -> 返回 200
    
    Args:
        request: 分析請求引數
        config: 配置依賴
        
    Returns:
        AnalysisResultResponse: 分析結果（同步模式）
        TaskAccepted | BatchTaskAcceptedResponse: 任務已接受（非同步模式，返回 202）
        
    Raises:
        HTTPException: 400 - 請求引數錯誤
        HTTPException: 409 - 股票正在分析中
        HTTPException: 500 - 分析失敗
    """
    # 校驗請求引數
    stock_codes = []
    if request.stock_code:
        stock_codes.append(request.stock_code)
    if request.stock_codes:
        stock_codes.extend(request.stock_codes)

    if not stock_codes:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "validation_error",
                "message": "必須提供 stock_code 或 stock_codes 引數"
            }
        )

    # 統一大小寫後去重，確保 ['aapl', 'AAPL'] 被識別為同一股票（Issue #355）
    stock_codes = [canonical_stock_code(c) for c in stock_codes]
    stock_codes = [c for c in stock_codes if c]
    stock_codes = list(dict.fromkeys(stock_codes))

    if not stock_codes:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "validation_error",
                "message": "股票程式碼不能為空或僅包含空白字元"
            }
        )

    # 同步模式僅支援單隻股票
    if not request.async_mode:
        if len(stock_codes) > 1:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "validation_error",
                    "message": "同步模式僅支援單隻股票分析，請使用 async_mode=true 進行批次分析"
                }
            )
        return _handle_sync_analysis(stock_codes[0], request)

    # 非同步模式：為每隻股票提交任務
    return _handle_async_analysis_batch(stock_codes, request)


def _handle_async_analysis_batch(
    stock_codes: list,
    request: AnalyzeRequest
) -> JSONResponse:
    """
    處理非同步分析請求（支援批次）
    
    為每隻股票提交任務到佇列，立即返回 202
    如果僅一隻股票且正在分析中，返回 409
    """
    task_queue = get_task_queue()
    accepted_tasks, duplicate_errors = task_queue.submit_tasks_batch(
        stock_codes=stock_codes,
        stock_name=None,
        report_type=request.report_type,
        force_refresh=request.force_refresh,
    )

    accepted = [
        BatchTaskAcceptedItem(
            task_id=task.task_id,
            stock_code=task.stock_code,
            status="pending",
            message=f"分析任務已加入佇列: {task.stock_code}",
        )
        for task in accepted_tasks
    ]
    duplicates = [
        BatchDuplicateTaskItem(
            stock_code=dup.stock_code,
            existing_task_id=dup.existing_task_id,
            message=str(dup),
        )
        for dup in duplicate_errors
    ]
    
    # 單隻股票且被拒絕：保持 409 相容性
    if len(stock_codes) == 1 and duplicates:
        dup = duplicates[0]
        error_response = DuplicateTaskErrorResponse(
            error="duplicate_task",
            message=dup.message,
            stock_code=dup.stock_code,
            existing_task_id=dup.existing_task_id,
        )
        return JSONResponse(
            status_code=409,
            content=error_response.model_dump()
        )
    
    # 單隻股票成功：保持原有響應格式相容性
    if len(stock_codes) == 1 and accepted:
        task_accepted = TaskAccepted(
            task_id=accepted[0].task_id,
            status="pending",
            message=accepted[0].message,
        )
        return JSONResponse(
            status_code=202,
            content=task_accepted.model_dump()
        )
    
    # 批次：返回彙總結果
    batch_response = BatchTaskAcceptedResponse(
        accepted=accepted,
        duplicates=duplicates,
        message=f"已提交 {len(accepted)} 個任務，{len(duplicates)} 個重複跳過",
    )
    return JSONResponse(
        status_code=202,
        content=batch_response.model_dump()
    )


def _handle_sync_analysis(
    stock_code: str,
    request: AnalyzeRequest
) -> AnalysisResultResponse:
    """
    處理同步分析請求
    
    直接執行分析，等待完成後返回結果
    """
    import uuid
    from src.services.analysis_service import AnalysisService
    
    query_id = uuid.uuid4().hex
    
    try:
        service = AnalysisService()
        result = service.analyze_stock(
            stock_code=stock_code,
            report_type=request.report_type,
            force_refresh=request.force_refresh,
            query_id=query_id
        )

        if result is None:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "analysis_failed",
                    "message": f"分析股票 {stock_code} 失敗"
                }
            )

        # 構建報告結構
        report_data = result.get("report", {})
        context_snapshot, fundamental_snapshot = _load_sync_fundamental_sources(
            query_id=query_id,
            stock_code=result.get("stock_code", stock_code),
        )
        report = _build_analysis_report(
            report_data,
            query_id,
            stock_code,
            result.get("stock_name"),
            context_snapshot=context_snapshot,
            fallback_fundamental_payload=fundamental_snapshot,
        )

        return AnalysisResultResponse(
            query_id=query_id,
            stock_code=result.get("stock_code", stock_code),
            stock_name=result.get("stock_name"),
            report=report.model_dump() if report else None,
            created_at=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"分析失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"分析過程發生錯誤: {str(e)}"
            }
        )


# ============================================================
# GET /tasks - 獲取任務列表
# ============================================================

@router.get(
    "/tasks",
    response_model=TaskListResponse,
    responses={
        200: {"description": "任務列表"},
    },
    summary="獲取分析任務列表",
    description="獲取當前所有分析任務，可按狀態篩選"
)
def get_task_list(
    status: Optional[str] = Query(
        None,
        description="篩選狀態：pending, processing, completed, failed（支援逗號分隔多個）"
    ),
    limit: int = Query(20, description="返回數量限制", ge=1, le=100),
) -> TaskListResponse:
    """
    獲取分析任務列表
    
    Args:
        status: 狀態篩選（可選）
        limit: 返回數量限制
        
    Returns:
        TaskListResponse: 任務列表響應
    """
    task_queue = get_task_queue()
    
    # 獲取所有任務
    all_tasks = task_queue.list_all_tasks(limit=limit)
    
    # 狀態篩選
    if status:
        status_list = [s.strip().lower() for s in status.split(",")]
        all_tasks = [t for t in all_tasks if t.status.value in status_list]
    
    # 統計資訊
    stats = task_queue.get_task_stats()
    
    # 轉換為 Schema
    task_infos = [
        TaskInfo(
            task_id=t.task_id,
            stock_code=t.stock_code,
            stock_name=t.stock_name,
            status=t.status.value,
            progress=t.progress,
            message=t.message,
            report_type=t.report_type,
            created_at=t.created_at.isoformat(),
            started_at=t.started_at.isoformat() if t.started_at else None,
            completed_at=t.completed_at.isoformat() if t.completed_at else None,
            error=t.error,
        )
        for t in all_tasks
    ]
    
    return TaskListResponse(
        total=stats["total"],
        pending=stats["pending"],
        processing=stats["processing"],
        tasks=task_infos,
    )


# ============================================================
# GET /tasks/stream - SSE 實時推送
# ============================================================

@router.get(
    "/tasks/stream",
    responses={
        200: {"description": "SSE 事件流", "content": {"text/event-stream": {}}},
    },
    summary="任務狀態 SSE 流",
    description="透過 Server-Sent Events 實時推送任務狀態變化"
)
async def task_stream():
    """
    SSE 任務狀態流
    
    事件型別：
    - connected: 連線成功
    - task_created: 新任務建立
    - task_started: 任務開始執行
    - task_completed: 任務完成
    - task_failed: 任務失敗
    - heartbeat: 心跳（每 30 秒）
    
    Returns:
        StreamingResponse: SSE 事件流
    """
    async def event_generator():
        task_queue = get_task_queue()
        event_queue: asyncio.Queue = asyncio.Queue()
        
        # 傳送連線成功事件
        yield _format_sse_event("connected", {"message": "Connected to task stream"})
        
        # 傳送當前進行中的任務
        pending_tasks = task_queue.list_pending_tasks()
        for task in pending_tasks:
            yield _format_sse_event("task_created", task.to_dict())
        
        # 訂閱任務事件
        task_queue.subscribe(event_queue)
        
        try:
            while True:
                try:
                    # 等待事件，超時傳送心跳
                    event = await asyncio.wait_for(event_queue.get(), timeout=30)
                    yield _format_sse_event(event["type"], event["data"])
                except asyncio.TimeoutError:
                    # 心跳
                    yield _format_sse_event("heartbeat", {
                        "timestamp": datetime.now().isoformat()
                    })
        except asyncio.CancelledError:
            # 客戶端斷開連線
            pass
        finally:
            task_queue.unsubscribe(event_queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 緩衝
        }
    )


def _format_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """
    格式化 SSE 事件
    
    Args:
        event_type: 事件型別
        data: 事件資料
        
    Returns:
        SSE 格式字串
    """
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ============================================================
# GET /status/{task_id} - 查詢單個任務狀態
# ============================================================

@router.get(
    "/status/{task_id}",
    response_model=TaskStatus,
    responses={
        200: {"description": "任務狀態"},
        404: {"description": "任務不存在", "model": ErrorResponse},
    },
    summary="查詢分析任務狀態",
    description="根據 task_id 查詢單個任務的狀態"
)
def get_analysis_status(task_id: str) -> TaskStatus:
    """
    查詢分析任務狀態
    
    優先從任務佇列查詢，如果不存在則從資料庫查詢歷史記錄
    
    Args:
        task_id: 任務 ID
        
    Returns:
        TaskStatus: 任務狀態資訊
        
    Raises:
        HTTPException: 404 - 任務不存在
    """
    # 1. 先從任務佇列查詢
    task_queue = get_task_queue()
    task = task_queue.get_task(task_id)
    
    if task:
        return TaskStatus(
            task_id=task.task_id,
            status=task.status.value,
            progress=task.progress,
            result=None,  # 進行中的任務沒有結果
            error=task.error,
        )
    
    # 2. 從資料庫查詢已完成的記錄
    try:
        from src.storage import DatabaseManager
        db = DatabaseManager.get_instance()
        records = db.get_analysis_history(query_id=task_id, limit=1)

        if records:
            record = records[0]
            raw_result = parse_json_field(record.raw_result)
            model_used = normalize_model_used(
                (raw_result or {}).get("model_used") if isinstance(raw_result, dict) else None
            )
            # Build report from DB record so completed tasks return real data
            report_dict = AnalysisReport(
                meta=ReportMeta(
                    id=record.id,
                    query_id=task_id,
                    stock_code=record.code,
                    stock_name=record.name,
                    report_type=getattr(record, 'report_type', None),
                    created_at=record.created_at.isoformat() if record.created_at else None,
                    model_used=model_used,
                ),
                summary=ReportSummary(
                    sentiment_score=record.sentiment_score,
                    operation_advice=record.operation_advice,
                    trend_prediction=record.trend_prediction,
                    analysis_summary=record.analysis_summary,
                ),
                strategy=ReportStrategy(
                    ideal_buy=str(getattr(record, 'ideal_buy', None)) if getattr(record, 'ideal_buy', None) is not None else None,
                    secondary_buy=str(getattr(record, 'secondary_buy', None)) if getattr(record, 'secondary_buy', None) is not None else None,
                    stop_loss=str(getattr(record, 'stop_loss', None)) if getattr(record, 'stop_loss', None) is not None else None,
                    take_profit=str(getattr(record, 'take_profit', None)) if getattr(record, 'take_profit', None) is not None else None,
                ),
            ).model_dump()
            return TaskStatus(
                task_id=task_id,
                status="completed",
                progress=100,
                result=AnalysisResultResponse(
                    query_id=task_id,
                    stock_code=record.code,
                    stock_name=record.name,
                    report=report_dict,
                    created_at=record.created_at.isoformat() if record.created_at else datetime.now().isoformat()
                ),
                error=None
            )

    except Exception as e:
        logger.error(f"查詢任務狀態失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"查詢任務狀態失敗: {str(e)}"
            }
        )

    # 3. 任務不存在
    raise HTTPException(
        status_code=404,
        detail={
            "error": "not_found",
            "message": f"任務 {task_id} 不存在或已過期"
        }
    )


# ============================================================
# 輔助函式
# ============================================================

def _load_sync_fundamental_sources(
    query_id: str,
    stock_code: str,
) -> tuple[Optional[Any], Optional[Dict[str, Any]]]:
    """
    Load context_snapshot and fallback fundamental snapshot for sync analyze response.
    """
    try:
        from src.storage import DatabaseManager

        db = DatabaseManager.get_instance()
        records = db.get_analysis_history(query_id=query_id, code=stock_code, limit=1)
        context_snapshot = None
        if records:
            context_snapshot = parse_json_field(getattr(records[0], "context_snapshot", None))

        fallback_fundamental = db.get_latest_fundamental_snapshot(
            query_id=query_id,
            code=stock_code,
        )
        return context_snapshot, fallback_fundamental
    except Exception as e:
        logger.debug(
            "load sync fundamental sources failed (fail-open): query_id=%s stock_code=%s err=%s",
            query_id,
            stock_code,
            e,
        )
        return None, None


def _build_analysis_report(
        report_data: Dict[str, Any],
        query_id: str,
        stock_code: str,
        stock_name: Optional[str] = None,
        context_snapshot: Optional[Any] = None,
        fallback_fundamental_payload: Optional[Dict[str, Any]] = None,
) -> AnalysisReport:
    """
    構建符合 API 規範的分析報告
    
    Args:
        report_data: 原始報告資料
        query_id: 查詢 ID
        stock_code: 股票程式碼
        stock_name: 股票名稱
        context_snapshot: 上下文快照（可選）
        fallback_fundamental_payload: 基本面快照 payload（可選）
        
    Returns:
        AnalysisReport: 結構化的分析報告
    """
    meta_data = report_data.get("meta", {})
    summary_data = report_data.get("summary", {})
    strategy_data = report_data.get("strategy", {})
    details_data = report_data.get("details", {})

    meta = ReportMeta(
        query_id=meta_data.get("query_id", query_id),
        stock_code=meta_data.get("stock_code", stock_code),
        stock_name=meta_data.get("stock_name", stock_name),
        report_type=meta_data.get("report_type", "detailed"),
        created_at=meta_data.get("created_at", datetime.now().isoformat()),
        current_price=meta_data.get("current_price"),
        change_pct=meta_data.get("change_pct"),
        model_used=normalize_model_used(meta_data.get("model_used")),
    )

    summary = ReportSummary(
        analysis_summary=summary_data.get("analysis_summary"),
        operation_advice=summary_data.get("operation_advice"),
        trend_prediction=summary_data.get("trend_prediction"),
        sentiment_score=summary_data.get("sentiment_score"),
        sentiment_label=summary_data.get("sentiment_label")
    )

    strategy = None
    if strategy_data:
        strategy = ReportStrategy(
            ideal_buy=strategy_data.get("ideal_buy"),
            secondary_buy=strategy_data.get("secondary_buy"),
            stop_loss=strategy_data.get("stop_loss"),
            take_profit=strategy_data.get("take_profit")
        )

    extracted_fundamental = extract_fundamental_detail_fields(
        context_snapshot=context_snapshot,
        fallback_fundamental_payload=fallback_fundamental_payload,
    )
    details = None
    if details_data or any(extracted_fundamental.values()) or context_snapshot is not None:
        details = ReportDetails(
            news_content=details_data.get("news_summary") or details_data.get("news_content"),
            raw_result=details_data,
            context_snapshot=context_snapshot,
            financial_report=extracted_fundamental.get("financial_report"),
            dividend_metrics=extracted_fundamental.get("dividend_metrics"),
        )

    return AnalysisReport(
        meta=meta,
        summary=summary,
        strategy=strategy,
        details=details
    )

# -*- coding: utf-8 -*-
"""
===================================
分析相關模型
===================================

職責：
1. 定義分析請求和響應模型
2. 定義任務狀態模型
3. 定義非同步任務佇列相關模型
"""

from typing import Optional, List, Any
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatusEnum(str, Enum):
    """任務狀態列舉"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalyzeRequest(BaseModel):
    """分析請求模型"""
    
    stock_code: Optional[str] = Field(
        None, 
        description="單隻股票程式碼", 
        example="600519"
    )
    stock_codes: Optional[List[str]] = Field(
        None, 
        description="多隻股票程式碼（與 stock_code 二選一）",
        example=["600519", "000858"]
    )
    report_type: str = Field(
        "detailed",
        description="報告型別：simple(精簡) / detailed(完整) / full(完整) / brief(簡潔)",
        pattern="^(simple|detailed|full|brief)$",
    )
    force_refresh: bool = Field(
        True,
        description="是否強制重新整理（忽略快取）"
    )
    async_mode: bool = Field(
        False,
        description="是否使用非同步模式"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "stock_code": "600519",
                "report_type": "detailed",
                "force_refresh": False,
                "async_mode": False
            }
        }


class AnalysisResultResponse(BaseModel):
    """分析結果響應模型"""
    
    query_id: str = Field(..., description="分析記錄唯一標識")
    stock_code: str = Field(..., description="股票程式碼")
    stock_name: Optional[str] = Field(None, description="股票名稱")
    report: Optional[Any] = Field(None, description="分析報告")
    created_at: str = Field(..., description="建立時間")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query_id": "abc123def456",
                "stock_code": "600519",
                "stock_name": "貴州茅臺",
                "report": {
                    "summary": {
                        "sentiment_score": 75,
                        "operation_advice": "持有"
                    }
                },
                "created_at": "2024-01-01T12:00:00"
            }
        }


class TaskAccepted(BaseModel):
    """非同步任務接受響應"""
    
    task_id: str = Field(..., description="任務 ID，用於查詢狀態")
    status: str = Field(
        ..., 
        description="任務狀態",
        pattern="^(pending|processing)$"
    )
    message: Optional[str] = Field(None, description="提示資訊")
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task_abc123",
                "status": "pending",
                "message": "Analysis task accepted"
            }
        }


class BatchTaskAcceptedItem(BaseModel):
    """批次非同步任務中的單個成功提交項。"""

    task_id: str = Field(..., description="任務 ID，用於查詢狀態")
    stock_code: str = Field(..., description="股票程式碼")
    status: str = Field(
        ...,
        description="任務狀態",
        pattern="^(pending|processing)$"
    )
    message: Optional[str] = Field(None, description="提示資訊")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task_abc123",
                "stock_code": "600519",
                "status": "pending",
                "message": "分析任務已加入佇列: 600519"
            }
        }


class BatchDuplicateTaskItem(BaseModel):
    """批次非同步任務中的重複提交項。"""

    stock_code: str = Field(..., description="股票程式碼")
    existing_task_id: str = Field(..., description="已存在的任務 ID")
    message: str = Field(..., description="錯誤資訊")

    class Config:
        json_schema_extra = {
            "example": {
                "stock_code": "600519",
                "existing_task_id": "task_existing_123",
                "message": "股票 600519 正在分析中 (task_id: task_existing_123)"
            }
        }


class BatchTaskAcceptedResponse(BaseModel):
    """批次非同步任務接受響應。"""

    accepted: List[BatchTaskAcceptedItem] = Field(default_factory=list, description="成功提交的任務列表")
    duplicates: List[BatchDuplicateTaskItem] = Field(default_factory=list, description="重複而跳過的任務列表")
    message: str = Field(..., description="彙總資訊")

    class Config:
        json_schema_extra = {
            "example": {
                "accepted": [
                    {
                        "task_id": "task_abc123",
                        "stock_code": "600519",
                        "status": "pending",
                        "message": "分析任務已加入佇列: 600519"
                    }
                ],
                "duplicates": [
                    {
                        "stock_code": "000858",
                        "existing_task_id": "task_existing_456",
                        "message": "股票 000858 正在分析中 (task_id: task_existing_456)"
                    }
                ],
                "message": "已提交 1 個任務，1 個重複跳過"
            }
        }


class TaskStatus(BaseModel):
    """任務狀態模型"""
    
    task_id: str = Field(..., description="任務 ID")
    status: str = Field(
        ..., 
        description="任務狀態",
        pattern="^(pending|processing|completed|failed)$"
    )
    progress: Optional[int] = Field(
        None, 
        description="進度百分比 (0-100)",
        ge=0,
        le=100
    )
    result: Optional[AnalysisResultResponse] = Field(
        None, 
        description="分析結果（僅在 completed 時存在）"
    )
    error: Optional[str] = Field(
        None, 
        description="錯誤資訊（僅在 failed 時存在）"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task_abc123",
                "status": "completed",
                "progress": 100,
                "result": None,
                "error": None
            }
        }


class TaskInfo(BaseModel):
    """
    任務詳情模型
    
    用於任務列表和 SSE 事件推送
    """
    
    task_id: str = Field(..., description="任務 ID")
    stock_code: str = Field(..., description="股票程式碼")
    stock_name: Optional[str] = Field(None, description="股票名稱")
    status: TaskStatusEnum = Field(..., description="任務狀態")
    progress: int = Field(0, description="進度百分比 (0-100)", ge=0, le=100)
    message: Optional[str] = Field(None, description="狀態訊息")
    report_type: str = Field("detailed", description="報告型別")
    created_at: str = Field(..., description="建立時間")
    started_at: Optional[str] = Field(None, description="開始執行時間")
    completed_at: Optional[str] = Field(None, description="完成時間")
    error: Optional[str] = Field(None, description="錯誤資訊（僅在 failed 時存在）")
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "abc123def456",
                "stock_code": "600519",
                "stock_name": "貴州茅臺",
                "status": "processing",
                "progress": 50,
                "message": "正在分析中...",
                "report_type": "detailed",
                "created_at": "2026-02-05T10:30:00",
                "started_at": "2026-02-05T10:30:01",
                "completed_at": None,
                "error": None
            }
        }


class TaskListResponse(BaseModel):
    """任務列表響應模型"""
    
    total: int = Field(..., description="任務總數")
    pending: int = Field(..., description="等待中的任務數")
    processing: int = Field(..., description="處理中的任務數")
    tasks: List[TaskInfo] = Field(..., description="任務列表")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total": 3,
                "pending": 1,
                "processing": 2,
                "tasks": []
            }
        }


class DuplicateTaskErrorResponse(BaseModel):
    """重複任務錯誤響應模型"""
    
    error: str = Field("duplicate_task", description="錯誤型別")
    message: str = Field(..., description="錯誤資訊")
    stock_code: str = Field(..., description="股票程式碼")
    existing_task_id: str = Field(..., description="已存在的任務 ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "duplicate_task",
                "message": "股票 600519 正在分析中",
                "stock_code": "600519",
                "existing_task_id": "abc123def456"
            }
        }
